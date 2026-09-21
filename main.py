import sys
import threading
from urllib.parse import urlparse

import redis
import structlog

from config import ConfigError, load_config
from health import start_health_server
from storage.cache import S3CacheClient
from storage.events import RedisEventEmitter


def _configure_logging(log_level: str) -> None:
    """
    Configure structlog to output JSON to stdout, one object per line.
    Every log call automatically includes timestamp, level, and message.
    job_id and profile_id are bound per-job via structlog.contextvars.
    """
    import logging

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
    )

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, log_level.upper(), logging.INFO),
    )


def _redis_host_only(redis_url: str) -> str:
    """Return only host:port from a Redis URL — never logs credentials."""
    try:
        parsed = urlparse(redis_url)
        return f"{parsed.hostname}:{parsed.port or 6379}"
    except Exception:
        return "(unparseable)"


def main() -> None:
    # 1. Load config — exit immediately listing ALL missing vars
    try:
        config = load_config()
    except ConfigError as e:
        # Use print here — logging not configured yet
        print(f"[CRITICAL] Configuration error: {e}", file=sys.stderr)
        sys.exit(1)

    # 2. Configure structlog — must happen before any logger calls
    _configure_logging(config.log_level)
    log = structlog.get_logger("seam_avatar")

    # 3. Startup banner
    log.info(
        "Starting seam_avatar",
        python_version=sys.version.split()[0],
        makehuman_data_path=config.makehuman_data_path,
        redis_host=_redis_host_only(config.redis_url),
        s3_bucket=config.avatar_cache_bucket,
    )

    # 4. Ready flag — health server reads this to decide /health/ready response
    ready_flag = threading.Event()

    # 5. Start health server in daemon thread immediately
    #    ECS health checks can hit /health right away; /health/ready returns 503
    #    until we set the flag at the end of startup
    start_health_server(config.health_port, ready_flag)

    # 6. Load the headless deformer — slow step (2–5 seconds, loads morph targets)
    #    Deferred import so the startup banner and health server start first
    log.info("Loading MakeHuman base mesh and morph targets")
    from pipeline.deform import HeadlessDeformer
    deformer = HeadlessDeformer(config.makehuman_data_path)
    log.info("Deformer ready")

    # 7. Verify Redis connectivity
    try:
        redis_client = redis.from_url(config.redis_url)
        redis_client.ping()
        log.info("Redis connection verified", host=_redis_host_only(config.redis_url))
    except redis.ConnectionError as e:
        log.critical("Cannot connect to Redis — aborting startup", error=str(e))
        sys.exit(1)

    # 8. Mark service as ready — /health/ready now returns 200
    ready_flag.set()
    log.info("Service ready")

    # 9. Build storage and event components
    cache = S3CacheClient(
        bucket=config.avatar_cache_bucket,
        region=config.aws_region,
        endpoint_url=config.aws_endpoint_url,
    )
    emitter = RedisEventEmitter(
        redis_client=redis_client,
        completed_channel=config.redis_completed_channel,
        failed_channel=config.redis_failed_channel,
    )

    # 10. Build worker and run — blocks here until KeyboardInterrupt or process kill
    from worker import AvatarWorker
    worker = AvatarWorker(
        config=config,
        deformer=deformer,
        cache=cache,
        emitter=emitter,
    )

    try:
        worker.run()
    except KeyboardInterrupt:
        log.info("Shutting down cleanly")


if __name__ == "__main__":
    main()
