FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-group test

ENV PATH="/app/.venv/bin:$PATH"

COPY alembic.ini ./
COPY migrations/ ./migrations/
COPY src ./src

# Shell form so that CELERY_* env vars are expanded at container start time.
CMD ["sh", "-c", "celery -A src.worker.celery_app worker --loglevel=info -Q ${CELERY_QUEUES:-light} -c ${CELERY_CONCURRENCY:-2} --max-memory-per-child=${CELERY_MAX_MEMORY_PER_CHILD:-200000}"]
