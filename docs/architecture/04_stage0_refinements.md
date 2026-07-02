### 04: Stage 0 Refinements & Infrastructure Hardening
**Version:** 0.1

##### Preamble
This document outlines refinements to the Stage 0 "Walking Skeleton" to harden the infrastructure before introducing the full domain schema. It addresses security, configuration defaults, and the dependency management strategy required for cloud-native scaling.

##### 1. Fail-Fast Secrets
*   **Directive:** Remove all plain-text fallback credentials from the codebase (e.g., in `docker-compose.yml` and `session.py`). 
*   **Behavior:** The application and infrastructure must strictly rely on environment variables injected via a `.env` file (or GitHub Secrets in CI). If database credentials are missing, the application must immediately crash ("Fail Fast") rather than silently booting with insecure defaults.

##### 2. Port Configuration
*   **Directive:** Preserve developer-friendly default host ports for standard services (FastAPI on 8000, Vite on 5173, Postgres on 5432, Redis on 6379) to allow zero-configuration local bootups.
*   **Refinement:** Parameterize the Flower monitoring port to use `${FLOWER_PORT:-5555}` in `docker-compose.yml` and add it to `.env.example`.

##### 3. Dependency Management Strategy
*   **Directive:** Transition standard Python microservices (API, UI backend, routing workers) from raw `requirements.txt` to a modern, fast package manager like `uv` or `poetry` to ensure exact lockfile reproducibility.
*   **Heavy Worker Exemption:** Heavy astronomical processing workers (e.g., those requiring C/Fortran libraries or complex dependencies like `jwst` and `space_phot`) are permitted to use `conda` (`environment.yml`) or separate dedicated `requirements.txt` files to avoid dependency hell. This aligns with the microservice worker-routing architecture.

##### 4. Data Persistence
*   **Directive:** Maintain the use of Docker named volumes (e.g., `diffpype_db_data`) for the PostgreSQL database. Because the architecture dictates an S3-based execution strategy—where heavy binary FITS files are kept in S3 and only relational metadata is stored in the database—the database will remain lightweight and will not saturate Docker Desktop's virtual disk limits.

#### Logging
The "Logs" section will record Claude's work. Please use the following format:
##### (Short summary of the work)
##### (Short summary of the work)
...
#### Logs

##### Fail-Fast Secrets, uv Migration, Port Config, & Data Persistence
*   Removed all plain-text credential fallbacks. `src/db/session.py` now uses `os.environ["DATABASE_URL"]` (raises `KeyError` on missing). `src/worker/celery_app.py` uses `os.environ["REDIS_URL"]`. `docker-compose.yml` credential vars (`POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`) stripped of `:-` defaults; `pg_isready` healthcheck updated likewise. Service port vars retain developer-friendly defaults (e.g., `${POSTGRES_PORT:-5432}`).
*   Parameterized Flower port: `docker-compose.yml` flower service now maps `${FLOWER_PORT:-5555}:5555`. Added `FLOWER_PORT=5555` to `.env.example` and `.env`.
*   Transitioned Python dependency management to `uv`. Created `pyproject.toml` (main deps + `[dependency-groups] test`). Ran `uv lock` to generate `uv.lock`. `docker/api.Dockerfile` and `docker/worker.Dockerfile` updated to copy the `uv` binary from `ghcr.io/astral-sh/uv:latest`, run `uv sync --frozen` (api includes test group; worker excludes it), and expose the venv via `ENV PATH="/app/.venv/bin:$PATH"`. `requirements.txt` deleted. Pytest configuration migrated from `pytest.ini` into `[tool.pytest.ini_options]` in `pyproject.toml`; `pytest.ini` deleted. `.github/workflows/ci.yml` updated to use `astral-sh/setup-uv` and `uv run pytest`, with dummy `DATABASE_URL`/`REDIS_URL` env vars so fail-fast imports succeed in the mock-only CI environment.
*   Docker named volume (`diffpype_db_data`) retained for Postgres persistence per directive 4.
*   **Verification:** `docker compose build api` succeeded. `pytest --cov=src --cov-report=term-missing --cov-fail-under=90` → 4 passed, 90.34% coverage (threshold met).
