FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /app

# Layer 1: install deps only (cached unless pyproject.toml/uv.lock change).
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --group test

# Layer 2: copy source then install the project so hatchling can build it
#           correctly and register the diffpype-manage entry-point script.
COPY alembic.ini ./
COPY migrations/ ./migrations/
COPY src ./src
RUN uv sync --frozen --group test

ENV PATH="/app/.venv/bin:$PATH"

CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
