import asyncio
import dataclasses
import signal
import time

import structlog
from bullmq import Worker

from config import Config
from errors import INVALID_PAYLOAD, AvatarError
from models import BodyMeasurements, JobPayload, JobResult
from pipeline.anchors import extract_anchors
from pipeline.calibration import calibrate
from pipeline.export import export_gltf
from pipeline.hash import compute_profile_hash
from storage.cache import S3CacheClient

logger = structlog.get_logger(__name__)


class AvatarWorker:
    """BullMQ worker for body-only avatar generation."""

    def __init__(self, config: Config, deformer, cache: S3CacheClient):
        self._config = config
        self._deformer = deformer
        self._cache = cache
        self._log = logger.bind(component="worker")

    def run(self) -> None:
        asyncio.run(self._run())

    async def _run(self) -> None:
        shutdown_event = asyncio.Event()
        loop = asyncio.get_running_loop()

        for signum in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(signum, shutdown_event.set)
            except (NotImplementedError, RuntimeError):
                pass

        worker = Worker(
            self._config.redis_queue_name,
            self._process_job,
            {
                "connection": self._config.redis_url,
                "prefix": self._config.bullmq_prefix,
                "name": "seam-avatar-worker",
                "concurrency": 1,
                "autorun": True,
            },
        )

        self._log.info(
            "BullMQ worker started",
            queue=self._config.redis_queue_name,
            prefix=self._config.bullmq_prefix,
        )

        try:
            await shutdown_event.wait()
        finally:
            self._log.info("Closing BullMQ worker")
            await worker.close()
            self._log.info("BullMQ worker closed")

    async def _process_job(self, job, _token=None):
        job_id = str(job.id)
        profile_id = None
        started_at = time.monotonic()

        try:
            if job.name != "generate-avatar":
                raise AvatarError(
                    INVALID_PAYLOAD,
                    f"Unsupported avatar job name: {job.name}",
                )

            payload = self._parse_payload(job.data, job_id)
            job_id = payload.job_id
            profile_id = payload.profile_id
            structlog.contextvars.bind_contextvars(job_id=job_id, profile_id=profile_id)
            self._log.info("Avatar job received")

            profile_hash = compute_profile_hash(payload.measurements)
            self._log.info("Profile hash computed", hash=profile_hash[:12] + "…")

            if self._cache.exists(profile_hash):
                result = JobResult(
                    job_id=job_id,
                    profile_id=profile_id,
                    avatar_version=payload.avatar_version,
                    profile_hash=profile_hash,
                    s3_key=f"avatars/cache/{profile_hash}.glb",
                    anchor_count=len(__import__("anchor_map").ANCHOR_MAP),
                    duration_ms=int((time.monotonic() - started_at) * 1000),
                    cache_hit=True,
                    deform_ms=0,
                    calibration_ms=0,
                    export_ms=0,
                    upload_ms=0,
                )
                self._log.info("Avatar cache hit", profile_hash=profile_hash)
                return dataclasses.asdict(result)

            t_calibrate = time.monotonic()
            modifier_dict, residuals = calibrate(
                payload.measurements,
                self._deformer,
                self._config.calibration_max_seconds,
            )
            calibration_ms = int((time.monotonic() - t_calibrate) * 1000)
            self._log.info("Calibration complete", residuals=residuals, ms=calibration_ms)

            t_deform = time.monotonic()
            self._deformer.apply_modifiers(modifier_dict)
            vertex_array = self._deformer.get_vertex_array()
            face_array = self._deformer.get_face_array()
            deform_ms = int((time.monotonic() - t_deform) * 1000)
            self._log.info("Deformation complete", ms=deform_ms)

            anchors = extract_anchors(vertex_array)

            t_export = time.monotonic()
            glb_bytes = export_gltf(vertex_array, face_array, anchors)
            export_ms = int((time.monotonic() - t_export) * 1000)
            self._log.info("Export complete", size_kb=len(glb_bytes) // 1024, ms=export_ms)

            t_upload = time.monotonic()
            s3_key = self._cache.upload(profile_hash, glb_bytes)
            upload_ms = int((time.monotonic() - t_upload) * 1000)
            self._log.info("S3 upload complete", key=s3_key, ms=upload_ms)

            result = JobResult(
                job_id=job_id,
                profile_id=profile_id,
                avatar_version=payload.avatar_version,
                profile_hash=profile_hash,
                s3_key=s3_key,
                anchor_count=len(anchors),
                duration_ms=int((time.monotonic() - started_at) * 1000),
                cache_hit=False,
                deform_ms=deform_ms,
                calibration_ms=calibration_ms,
                export_ms=export_ms,
                upload_ms=upload_ms,
            )
            self._log.info("Avatar job complete", **dataclasses.asdict(result))
            return dataclasses.asdict(result)

        except AvatarError as error:
            self._log.error("Avatar job failed", error=error.code, detail=error.detail)
            raise
        except Exception as error:  # noqa: BLE001 — BullMQ must see the failure for retry
            self._log.exception("Avatar job failed", error=str(error))
            raise
        finally:
            self._deformer.reset()
            structlog.contextvars.clear_contextvars()

    def _parse_payload(self, data: dict, fallback_job_id: str) -> JobPayload:
        if not isinstance(data, dict):
            raise AvatarError(INVALID_PAYLOAD, "BullMQ job data must be an object")

        missing = [field for field in ("profile_id", "measurements") if field not in data]
        if missing:
            raise AvatarError(
                INVALID_PAYLOAD,
                f"Missing required fields: {', '.join(missing)}",
            )

        try:
            measurements = BodyMeasurements.from_tmm_dict(data["measurements"])
        except Exception as error:
            raise AvatarError(INVALID_PAYLOAD, f"Invalid measurements: {error}") from error

        return JobPayload(
            job_id=str(data.get("job_id") or fallback_job_id),
            profile_id=str(data["profile_id"]),
            avatar_version=str(data.get("avatar_version") or "fixed-avatar-v1"),
            measurements=measurements,
        )
