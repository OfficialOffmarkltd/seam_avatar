import os
from dataclasses import dataclass


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Config:
    # Required
    redis_url: str
    avatar_cache_bucket: str
    makehuman_data_path: str
    aws_region: str
    # Optional with defaults
    redis_queue_name: str        = "seam_avatar:jobs"
    redis_dead_letter_queue: str = "seam_avatar:jobs:dead"
    redis_completed_channel: str = "seam_avatar:completed"
    redis_failed_channel: str    = "seam_avatar:failed"
    calibration_max_seconds: int = 5
    job_max_retries: int         = 3
    log_level: str               = "INFO"
    aws_endpoint_url: str | None = None
    health_port: int             = 8081


def load_config() -> Config:
    """
    Reads all required env vars. Raises ConfigError listing ALL missing variables
    if any required var is absent. Never returns a partially-valid Config.
    """
    REQUIRED = [
        "REDIS_URL",
        "AVATAR_CACHE_BUCKET",
        "MAKEHUMAN_DATA_PATH",
        "AWS_REGION",
    ]

    missing = [key for key in REQUIRED if not os.environ.get(key)]
    if missing:
        raise ConfigError(
            f"Missing required environment variables: {', '.join(missing)}"
        )

    # Parse optional numeric vars — raise clearly if they are set but not valid integers
    def get_int(key: str, default: int) -> int:
        val = os.environ.get(key)
        if val is None:
            return default
        try:
            return int(val)
        except ValueError:
            raise ConfigError(
                f"Environment variable {key} must be an integer, got: {val!r}"
            )

    def _validated_port(port: int) -> int:
        if not (1 <= port <= 65535):
            raise ConfigError(
                f"HEALTH_PORT must be in the range 1..65535, got: {port}"
            )
        return port

    return Config(
        redis_url               = os.environ["REDIS_URL"],
        avatar_cache_bucket     = os.environ["AVATAR_CACHE_BUCKET"],
        makehuman_data_path     = os.environ["MAKEHUMAN_DATA_PATH"],
        aws_region              = os.environ["AWS_REGION"],
        redis_queue_name        = os.environ.get("REDIS_QUEUE_NAME",        "seam_avatar:jobs"),
        redis_dead_letter_queue = os.environ.get("REDIS_DEAD_LETTER_QUEUE", "seam_avatar:jobs:dead"),
        redis_completed_channel = os.environ.get("REDIS_COMPLETED_CHANNEL", "seam_avatar:completed"),
        redis_failed_channel    = os.environ.get("REDIS_FAILED_CHANNEL",    "seam_avatar:failed"),
        calibration_max_seconds = get_int("CALIBRATION_MAX_SECONDS", 5),
        job_max_retries         = get_int("JOB_MAX_RETRIES",          3),
        log_level               = os.environ.get("LOG_LEVEL",               "INFO"),
        aws_endpoint_url        = os.environ.get("AWS_ENDPOINT_URL"),
        health_port             = _validated_port(get_int("HEALTH_PORT", 8081)),
    )
