# seam_avatar

Parametric 3D avatar mesh service for [Seam](https://seam.app) by Offmark NIG LTD.

Takes a set of body measurements, deforms a human body mesh to match them using MakeHuman's morphing engine, and exports the result as a binary glTF (`.glb`) to S3. The mesh is cached forever under a content-addressed key — deformation only runs once per unique measurement set.

This service is published as open source to satisfy the AGPL-3.0 licence of MakeHuman. See [ADR-001](https://github.com/offmark/seam_docs/blob/main/docs/adr/ADR-001-avatar-model.md) for the full rationale.

---

## How it fits into Seam

```
seam_backend  ──RPUSH──►  Redis queue  ──►  seam_avatar  ──►  S3 (.glb cache)
                                                                    │
seam_backend  ◄── pub/sub completion event ─────────────────────────┘
                          │
                    seam_backend fetches .glb from S3
                    and uses it as the TPS deformation surface
```

`seam_backend` submits a job with a `BodyMeasurements` JSON payload. `seam_avatar` deforms the mesh, extracts named anatomical anchor points, exports a `.glb` with the anchors embedded in `scene.extras`, uploads to S3, and publishes a completion event. In steady state — when the measurement profile has been seen before — `seam_avatar` is not called at all. `seam_backend` fetches the cached `.glb` directly from S3.

---

## What the output contains

Each `.glb` contains:

- A triangulated human body mesh (minimum 5,000 faces), deformed to match the input measurements
- Vertex normals
- 25 named `AvatarAnchor` points embedded in `scene.extras.avatar_anchors` — specific anatomical positions (shoulders, underarms, chest, waist, hip, crotch, knees, wrists) that `seam_backend` uses as TPS landmark targets when draping garment pattern pieces

---

## Requirements

- Python 3.11+
- Access to a Redis instance
- AWS S3 bucket (or LocalStack for local development)
- MakeHuman data assets (see [Fetching MakeHuman data](#fetching-makehuman-data))

---

## Setup

```bash
git clone https://github.com/offmark/seam_avatar
cd seam_avatar
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### Fetching MakeHuman data

The MakeHuman morph targets and base mesh are not committed to this repo (they are large binary assets). Run the fetch script after cloning:

```bash
bash scripts/fetch_mh_data.sh
```

This downloads and compiles the required files into `vendor/makehuman/data/`. It requires `git` with LFS support.

---

## Configuration

All configuration is via environment variables. The service refuses to start if any required variable is missing, and lists all missing variables at once.

### Required

| Variable | Description |
|---|---|
| `REDIS_URL` | Redis connection string, e.g. `redis://localhost:6379/0` |
| `AVATAR_CACHE_BUCKET` | S3 bucket name for `.glb` cache |
| `MAKEHUMAN_DATA_PATH` | Absolute path to MakeHuman data directory |
| `AWS_REGION` | AWS region for S3 operations |

### Optional

| Variable | Default | Description |
|---|---|---|
| `REDIS_QUEUE_NAME` | `seam_avatar:jobs` | Queue key to pop jobs from |
| `REDIS_DEAD_LETTER_QUEUE` | `seam_avatar:jobs:dead` | Dead-letter queue key |
| `REDIS_COMPLETED_CHANNEL` | `seam_avatar:completed` | Pub/sub completion channel |
| `REDIS_FAILED_CHANNEL` | `seam_avatar:failed` | Pub/sub failure channel |
| `CALIBRATION_MAX_SECONDS` | `5` | Optimisation time budget per job |
| `JOB_MAX_RETRIES` | `3` | Retries before dead-letter |
| `LOG_LEVEL` | `INFO` | Python logging level |
| `AWS_ENDPOINT_URL` | — | S3 endpoint override (LocalStack) |
| `HEALTH_PORT` | `8081` | Port for health check HTTP server |

AWS credentials are read from the standard credential chain (instance profile in production; `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` for local development).

---

## Running locally

```bash
docker compose up
```

This starts `seam_avatar`, Redis, and LocalStack (S3). The service is ready when `GET http://localhost:8081/health/ready` returns `200`.

To run the end-to-end smoke test against the compose stack:

```bash
python scripts/smoke_test.py
```

---

## Job payload format

`seam_backend` pushes jobs as JSON to the `seam_avatar:jobs` Redis list. All measurement fields use tenths-of-mm integers with `_tmm` suffix (e.g. `chest_tmm: 1080` = 108.0mm):

```json
{
  "job_id":     "550e8400-e29b-41d4-a716-446655440000",
  "profile_id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
  "measurements": {
    "height_tmm":          17200,
    "chest_tmm":           10600,
    "waist_tmm":            8200,
    "full_hip_tmm":        10400,
    "shoulder_width_tmm":   4400
  }
}
```

Any field not provided is treated as `null` — the service proceeds with whatever measurements are available.

## Completion event format

Published to `seam_avatar:completed` on success:

```json
{
  "job_id":       "550e8400-e29b-41d4-a716-446655440000",
  "profile_id":   "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
  "profile_hash": "a3f8b2c1d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1",
  "s3_key":       "avatars/cache/a3f8b2c1...glb",
  "anchor_count": 25,
  "cache_hit":    false
}
```

---

## Health checks

| Endpoint | Purpose |
|---|---|
| `GET /health` | Liveness — returns `200` if the process is running |
| `GET /health/ready` | Readiness — returns `200` when mesh data is loaded and Redis is reachable; `503` while initialising |

---

## Tests

```bash
# Fast unit tests only
pytest tests/ -m "not integration"

# All tests including integration (requires MAKEHUMAN_DATA_PATH)
pytest tests/
```

Integration tests are marked with `@pytest.mark.integration` and require the MakeHuman data assets to be present. They are excluded from CI's fast test run.

---

## Licence

The `seam_avatar` service code is licensed under **AGPL-3.0** — matching the licence of MakeHuman, whose core modules are vendored in `vendor/makehuman/`.

The MakeHuman base mesh and morph target assets (`vendor/makehuman/data/`) are licensed under **CC0 1.0 Universal** by the MakeHuman community.

All other Seam services (`seam_backend`, `seam_frontend`, `seam_render`) are proprietary. They communicate with `seam_avatar` over HTTP/Redis and are not subject to AGPL. See [ADR-001](https://github.com/offmark/seam_docs/blob/main/docs/adr/ADR-001-avatar-model.md) for the legal reasoning.
