FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-group test

ENV PATH="/app/.venv/bin:$PATH"

COPY alembic.ini ./
COPY migrations/ ./migrations/
COPY src ./src

CMD ["celery", "-A", "src.worker.celery_app", "worker", "--loglevel=info", "-Q", "light"]
