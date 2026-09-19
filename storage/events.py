import json
import logging
from datetime import datetime, timezone
from typing import Any

import redis
from redis.exceptions import RedisError

from models import JobResult

logger = logging.getLogger(__name__)

class RedisEventEmitter:
    def __init__(self, redis_client: redis.Redis, completed_channel: str, failed_channel: str):
        self._client = redis_client
        self._completed_channel = completed_channel
        self._failed_channel = failed_channel

    def _publish(self, event: str, payload: dict[str, Any], channel: str) -> None:
        message = {
            "event": event,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **payload,
        }
        try:
            self._client.publish(channel, json.dumps(message))
        except RedisError:
            logger.exception(f"[RedisEventEmitter] Failed to publish to {channel}",)
        except Exception:
            logger.exception(f"[RedisEventEmitter] Unexpected error publishing to {channel}",)

    def emit_completed(self, payload: JobResult):
        import dataclasses
        return self._publish(
            event="completed", 
            payload=dataclasses.asdict(payload), 
            channel=self._completed_channel
        )

    def emit_failed(self, job_id: str, profile_id: str, error: str, detail: str):
        return self._publish(
            event="failed",
            payload={
                "job_id": job_id,
                "profile_id": profile_id,
                "error": error,
                "detail": detail,
            },
            channel=self._failed_channel,
        )