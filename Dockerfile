# ── Stage 1: dependencies ────────────────────────────────────────────────────
# Use a full image to compile scipy and other C-extension packages,
# then copy only the installed site-packages into the slim runtime image.
FROM python:3.11-slim AS builder

WORKDIR /build

# Install build tools needed to compile scipy, numpy, and trimesh extensions
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        g++ \
        gfortran \
        libopenblas-dev \
        pkg-config \
    && rm -rf /var/lib/apt/lists/*

# Copy and install dependencies — excluding dev tools (pytest, ruff, pyright)
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install \
    $(grep -v '^\s*#' requirements.txt | grep -v 'pytest' | grep -v 'ruff' | grep -v 'pyright')


# ── Stage 2: runtime ──────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application source
COPY anchor_map.py     .
COPY config.py         .
COPY errors.py         .
COPY health.py         .
COPY main.py           .
COPY models.py         .
COPY worker.py         .
COPY pipeline/         pipeline/
COPY storage/          storage/
COPY vendor/makehuman/ vendor/makehuman/

# MakeHuman data directory — large binary assets (targets.npz, base.obj)
# These are not committed to the repo. Mount at runtime or bake in here.
# Default path expected by getpath.py stub via MAKEHUMAN_DATA_PATH env var.
ENV MAKEHUMAN_DATA_PATH=/app/vendor/makehuman/data

# Health check port
EXPOSE 8081

# Run as non-root for security
RUN useradd --no-create-home --shell /bin/false seam
USER seam

CMD ["python", "main.py"]
