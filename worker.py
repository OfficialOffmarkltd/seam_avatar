import json
import logging
import time

import redis
import structlog

from config import Config
from errors import AvatarError, INVALID_PAYLOAD
from models import BodyMeasurements, JobPayload, JobResult
from pipeline.hash import compute_profile_hash
from pipeline.anchors import extract_anchors
from pipeline.export import export_gltf
from pipeline.calibration import calibrate
from storage.cache import S3CacheClient
from storage.events import RedisEventEmitter

logger = structlog.get_logger(__name__)


class AvatarWorker:

    def __init__(
        self,
        config: Config,
        deformer,           # HeadlessDeformer — imported lazily in main.py
        cache: S3CacheClient,
        emitter: RedisEventEmitter,
    ):
        self._config  = config
        self._deformer = deformer
        self._cache   = cache
        self._emitter = emitter
        self._redis   = redis.from_url(config.redis_url)
        self._log     = logger.bind(component="worker")

    # ── main loop ─────────────────────────────────────────────────────────────

    def run(self) -> None:
        """
        Block on the Redis queue and process jobs one at a time.
        Runs until KeyboardInterrupt or process kill.
        """
        self._log.info("Worker started", queue=self._config.redis_queue_name)

        while True:
            try:
                result = self._redis.blpop(
                    self._config.redis_queue_name,
                    timeout=5,
                )
            except redis.ConnectionError as e:
                self._log.error("Redis connection lost — retrying in 5s", error=str(e))
                time.sleep(5)
                continue

            if result is None:
                # timeout — loop again, allows clean KeyboardInterrupt handling
                continue

            _, raw_payload = result
            self._process_job(raw_payload.decode("utf-8"))

    # ── job processing ────────────────────────────────────────────────────────

    def _process_job(self, raw_payload: str) -> None:
        """
        Full 11-step pipeline for a single job.
        Any exception is caught, logged, and reported via the failure channel.
        The worker loop continues regardless.
        """
        job_id     = None
        profile_id = None
        started_at = time.monotonic()

        try:
            # Step 1 — parse and validate payload
            payload = self._parse_payload(raw_payload)
            job_id     = payload.job_id
            profile_id = payload.profile_id

            # Bind job context to all subsequent log calls
            structlog.contextvars.bind_contextvars(
                job_id=job_id,
                profile_id=profile_id,
            )
            self._log.info("Job received")

            # Step 2 — convert _tmm fields (already done in from_tmm_dict)
            measurements = payload.measurements

            # Step 3 — compute profile hash
            t0 = time.monotonic()
            profile_hash = compute_profile_hash(measurements)
            self._log.info("Profile hash computed", hash=profile_hash[:12] + "…")

            # Step 4 — check S3 cache
            if self._cache.exists(profile_hash):
                self._log.info("Cache hit — skipping deformation")
                self._emitter.emit_completed(JobResult(
                    job_id=job_id,
                    profile_id=profile_id,
                    profile_hash=profile_hash,
                    s3_key=f"avatars/cache/{profile_hash}.glb",
                    anchor_count=len(__import__("anchor_map").ANCHOR_MAP),
                    duration_ms=int((time.monotonic() - started_at) * 1000),
                    cache_hit=True,
                    deform_ms=0,
                    calibration_ms=0,
                    export_ms=0,
                    upload_ms=0,
                ))
                return

            # Step 5 — calibrate: measurements → modifier dict
            t_calibrate = time.monotonic()
            modifier_dict, residuals = calibrate(
                measurements,
                self._deformer,
                self._config.calibration_max_seconds,
            )
            calibration_ms = int((time.monotonic() - t_calibrate) * 1000)
            self._log.info("Calibration complete", residuals=residuals, ms=calibration_ms)

            # Step 6 — deform mesh
            t_deform = time.monotonic()
            self._deformer.apply_modifiers(modifier_dict)
            vertex_array = self._deformer.get_vertex_array()
            face_array   = self._deformer.get_face_array()
            deform_ms = int((time.monotonic() - t_deform) * 1000)
            self._log.info("Deformation complete", ms=deform_ms)

            # Step 7 — extract anchors
            anchors = extract_anchors(vertex_array)

            # Step 8 — export .glb
            t_export = time.monotonic()
            glb_bytes = export_gltf(vertex_array, face_array, anchors)
            export_ms = int((time.monotonic() - t_export) * 1000)
            self._log.info("Export complete", size_kb=len(glb_bytes) // 1024, ms=export_ms)

            # Step 9 — upload to S3
            t_upload = time.monotonic()
            s3_key = self._cache.upload(profile_hash, glb_bytes)
            upload_ms = int((time.monotonic() - t_upload) * 1000)
            self._log.info("S3 upload complete", key=s3_key, ms=upload_ms)

            # Step 10 — emit completion event
            duration_ms = int((time.monotonic() - started_at) * 1000)
            result = JobResult(
                job_id=job_id,
                profile_id=profile_id,
                profile_hash=profile_hash,
                s3_key=s3_key,
                anchor_count=len(anchors),
                duration_ms=duration_ms,
                cache_hit=False,
                deform_ms=deform_ms,
                calibration_ms=calibration_ms,
                export_ms=export_ms,
                upload_ms=upload_ms,
            )
            self._emitter.emit_completed(result)

            # Step 11 — summary log
            self._log.info(
                "Job complete",
                duration_ms=duration_ms,
                cache_hit=False,
                deform_ms=deform_ms,
                calibration_ms=calibration_ms,
                export_ms=export_ms,
                upload_ms=upload_ms,
            )

        except AvatarError as e:
            self._handle_failure(job_id, profile_id, raw_payload, e.code, e.detail)

        except Exception as e:
            self._handle_failure(job_id, profile_id, raw_payload, "INTERNAL_ERROR", str(e))

        finally:
            # Always reset deformer and clear log context between jobs
            self._deformer.reset()
            structlog.contextvars.clear_contextvars()

    # ── helpers ───────────────────────────────────────────────────────────────

    def _parse_payload(self, raw: str) -> JobPayload:
        """
        Parse raw JSON from the Redis queue into a JobPayload.
        Raises AvatarError(INVALID_PAYLOAD) on any parse or validation error.
        """
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            raise AvatarError(INVALID_PAYLOAD, f"Invalid JSON: {e}") from e

        missing = [f for f in ("job_id", "profile_id", "measurements") if f not in data]
        if missing:
            raise AvatarError(
                INVALID_PAYLOAD,
                f"Missing required fields: {', '.join(missing)}",
            )

        try:
            measurements = BodyMeasurements.from_tmm_dict(data["measurements"])
        except Exception as e:
            raise AvatarError(INVALID_PAYLOAD, f"Invalid measurements: {e}") from e

        return JobPayload(
            job_id=str(data["job_id"]),
            profile_id=str(data["profile_id"]),
            measurements=measurements,
        )

    def _handle_failure(
        self,
        job_id: str | None,
        profile_id: str | None,
        raw_payload: str,
        error_code: str,
        detail: str,
    ) -> None:
        """
        Log the failure, emit the failure event, and increment the retry counter.
        Move to dead-letter queue if retries are exhausted.
        """
        self._log.error("Job failed", error=error_code, detail=detail)

        safe_job_id     = job_id     or "unknown"
        safe_profile_id = profile_id or "unknown"

        self._emitter.emit_failed(
            job_id=safe_job_id,
            profile_id=safe_profile_id,
            error=error_code,
            detail=detail,
        )

        retry_count = self._increment_retry(safe_job_id)
        if retry_count >= self._config.job_max_retries:
            self._move_to_dead_letter(raw_payload, f"{error_code}: {detail}")
        else:
            self._log.warning(
                "Job will retry",
                retry=retry_count,
                max=self._config.job_max_retries,
            )

    def _increment_retry(self, job_id: str) -> int:
        """Increment and return the retry counter for a job. Stored in Redis."""
        key = f"seam_avatar:retries:{job_id}"
        count = self._redis.incr(key)
        # Expire after 24 hours so stale counters don't accumulate
        self._redis.expire(key, 86400)
        return int(count)

    def _move_to_dead_letter(self, raw_payload: str, reason: str) -> None:
        """Push the raw payload to the dead-letter queue and log at ERROR."""
        self._log.error(
            "Moving job to dead-letter queue",
            reason=reason,
            queue=self._config.redis_dead_letter_queue,
        )
        self._redis.rpush(self._config.redis_dead_letter_queue, raw_payload)
