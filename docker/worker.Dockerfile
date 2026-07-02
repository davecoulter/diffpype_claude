FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /app

# Layer 1: install deps only (cached unless pyproject.toml/uv.lock change).
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-group test

# Layer 2: copy source then install the project so hatchling can build it
#           correctly and register the diffpype-manage entry-point script.
COPY alembic.ini ./
COPY migrations/ ./migrations/
COPY src ./src
RUN uv sync --frozen --no-group test

ENV PATH="/app/.venv/bin:$PATH"

# Shell form so that CELERY_* env vars are expanded at container start time.
CMD ["sh", "-c", "celery -A src.worker.celery_app worker --loglevel=info -Q ${CELERY_QUEUES:-light} -c ${CELERY_CONCURRENCY:-2} --max-memory-per-child=${CELERY_MAX_MEMORY_PER_CHILD:-200000}"]
