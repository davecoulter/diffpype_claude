FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# MinIO client (`mc`), used by run_staging_sync's `mc mirror` staging->canonical
# sync (doc 30 §1). Arch-aware so the image builds on both CI's linux/amd64 and
# an Apple-Silicon linux/arm64 build. Only the worker image gets `mc` — the api
# image never runs the sync (it is dispatched to the worker).
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && curl -fsSL "https://dl.min.io/client/mc/release/linux-$(dpkg --print-architecture)/mc" \
        -o /usr/local/bin/mc \
    && chmod +x /usr/local/bin/mc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Layer 1: install deps only (cached unless pyproject.toml/uv.lock change).
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-group test

# Layer 2: copy source then install the project so hatchling can build it
#           correctly and register the diffpype-manage entry-point script.
# Note: no alembic.ini/migrations/ here — the worker never runs alembic;
# only the api container does (docker compose exec api alembic upgrade head).
COPY src ./src
RUN uv sync --frozen --no-group test

ENV PATH="/app/.venv/bin:$PATH"

# Shell form so that CELERY_* env vars are expanded at container start time.
CMD ["sh", "-c", "celery -A src.worker.celery_app worker --loglevel=info -Q ${CELERY_QUEUES:-light} -c ${CELERY_CONCURRENCY:-2} --max-memory-per-child=${CELERY_MAX_MEMORY_PER_CHILD:-200000}"]
