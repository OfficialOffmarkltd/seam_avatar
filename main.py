import logging
import sys
import threading

import redis

from config import ConfigError, load_config
from health import start_health_server

# ---------------------------------------------------------------------------
# Logging — stdlib for now, replaced with structlog in task 3.4
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("seam_avatar")


def main() -> None:
    # 1. Load config — exit immediately if any required var is missing
    try:
        config = load_config()
    except ConfigError as e:
        logger.critical(f"Configuration error: {e}")
        sys.exit(1)

    # 2. Startup banner
    logger.info(
        "Starting seam_avatar",
        extra={
            "python_version": sys.version,
            "makehuman_data_path": config.makehuman_data_path,
            "s3_bucket": config.avatar_cache_bucket,
        },
    )

    # 3. Ready flag — health server uses this to report readiness
    ready_flag = threading.Event()

    # 4. Start health server in daemon thread before anything else
    #    so ECS can see /health immediately even while we're loading
    start_health_server(config.health_port, ready_flag)

    # 5. Load the headless deformer — this is the slow step (2–5 seconds)
    #    Import is deferred here so startup banner and health server come first
    logger.info("Loading MakeHuman base mesh and morph targets…")
    # from pipeline.deform import HeadlessDeformer
    # deformer = HeadlessDeformer(config.makehuman_data_path)
    # logger.info("Deformer ready")

    # 6. Verify Redis connectivity before marking ready
    try:
        redis_client = redis.from_url(config.redis_url)
        redis_client.ping()
        logger.info("Redis connection verified")
    except redis.ConnectionError as e:
        logger.critical(f"Cannot connect to Redis: {e}")
        sys.exit(1)

    # 7. Mark service as ready — /health/ready now returns 200
    ready_flag.set()
    logger.info("Service ready")

    # 8. Build storage and event components
    # cache = S3CacheClient(
    #     bucket=config.avatar_cache_bucket,
    #     region=config.aws_region,
    #     endpoint_url=config.aws_endpoint_url,
    # )
    # emitter = RedisEventEmitter(
    #     redis_client=redis_client,
    #     completed_channel=config.redis_completed_channel,
    #     failed_channel=config.redis_failed_channel,
    # )

    # 9. Build worker and run — blocks here until KeyboardInterrupt or process kill
    # from worker import AvatarWorker
    # worker = AvatarWorker(config=config, deformer=deformer, cache=cache, emitter=emitter)

    # try:
    #     worker.run()
    # except KeyboardInterrupt:
    #     logger.info("Shutting down cleanly")


if __name__ == "__main__":
    main()
