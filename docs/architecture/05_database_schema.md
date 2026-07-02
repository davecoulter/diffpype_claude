### 05: Database Schema & Migrations (Alembic Foundation)
**Version:** 0.2

##### Preamble
This document dictates the transition from the Stage 0 dummy database tables to a strict Alembic-managed migration pipeline. The core astronomical domain schema will be introduced in a subsequent stage.

##### 1. Alembic Migrations & Database Reset
*   **Directive:** Deprecate the use of `Base.metadata.create_all(bind=engine)` in `src/db/seed.py`.
*   **Behavior:** The project must now strictly rely on **Alembic** to manage database state. The human developer has already destroyed the legacy database volume. Claude must initialize an Alembic environment and generate the initial migration (`revision --autogenerate`) for the existing Stage 0 schema (`StepDefinition` and `DummyImage`). The CI/CD pipeline must be updated to run `alembic upgrade head` prior to executing `pytest`.

##### 2. Enumerations (DRY Principle)
*   **Directive:** Do not use raw strings for bounded choices. 
*   **Behavior:** Refactor the existing Stage 0 models (`DummyImage.status`, `StepDefinition.queue`) to use standard Python `enum.Enum` classes and map them to SQLAlchemy's `Enum` column type. 

##### 3. Spatial Indexing & Q3C Integration (Infrastructure Prep)
*   **Directive:** To prepare for the upcoming astronomical schema, standard Postgres cannot be used.
*   **Behavior:** 
    1. Replace the vanilla Postgres image in `docker-compose.yml` with a custom build targeting `docker/db.Dockerfile`.
    2. Write `docker/db.Dockerfile` to download, compile, and install the Q3C C-extension from source into the Postgres container.
    3. Add `healpix-alchemy` to the modern package manager lockfile to handle the future ORM mapping.

#### Logging
The "Logs" section will record Claude's work. Please use the following format:
##### (Short summary of the work)
##### (Short summary of the work)
...
#### Logs

##### Alembic Foundation, Enum Refactor, & Q3C Infrastructure
*   **Alembic:** Added `alembic==1.13.3` to `pyproject.toml`. Initialized `alembic.ini` (no hardcoded `sqlalchemy.url`; credentials injected via `os.environ["DATABASE_URL"]` in `migrations/env.py`) and `migrations/script.py.mako`. Wrote the initial migration `migrations/versions/20260702_0001_initial_schema.py` — creates native Postgres enum types (`celery_queue`, `dummy_image_status`), then creates `step_definitions` and `dummy_images` tables using those types. `src/db/seed.py` refactored to remove `Base.metadata.create_all()`; now only seeds the `StepDefinition` dummy row (renamed entry point to `seed_step_definitions`). `src/api/main.py` lifespan updated to call `alembic command.upgrade("head")` then `seed_step_definitions()`.
*   **Enumerations:** Created `src/db/enums.py` with `DummyImageStatus(str, enum.Enum)` (`Pending/Running/Success/Failed`) and `CeleryQueue(str, enum.Enum)` (`light/heavy_memory/gpu/external`). Updated `src/db/models.py` to use `sa.Enum(..., create_type=False)` mapped columns. Updated `src/worker/tasks.py` to assign `DummyImageStatus.SUCCESS`. `str` mixin ensures string comparisons and JSON serialization remain unchanged.
*   **Q3C Infrastructure:** Created `docker/db.Dockerfile` based on `postgres:16` (Debian). Installs build deps (`build-essential`, `postgresql-server-dev-16`, `libreadline-dev`, `libzstd-dev`, `liblz4-dev`, `zlib1g-dev`, `libssl-dev`), downloads Q3C v2.0.1 from source, runs `make && make install`, cleans build artifacts. `docker-compose.yml` `db` service switched from `image: postgres:16-alpine` to `build: docker/db.Dockerfile`. Added `healpix-alchemy==1.0.1` to `pyproject.toml`; `uv.lock` regenerated.
*   **Test Isolation:** Added `src/api/tests/conftest.py` with an `autouse` fixture that patches `command.upgrade` and `seed_step_definitions` so unit tests remain fully isolated (no real DB connection at startup). CI workflow updated to provide a `postgres:16` service container and run `alembic upgrade head` explicitly before `pytest`; `DATABASE_URL` now points to the CI postgres service.
*   **Verification:** `docker compose build db api` succeeded (Q3C compiled cleanly). `pytest --cov=src --cov-fail-under=90` → 4 passed, 91.07% coverage.
