##### 11: Shared Service Layer Refactoring
**Version:** 0.1

###### Preamble
This document dictates the refactoring of the Stage 0 API and CLI to implement the Shared Service Layer architecture defined in the updated `01_system_architecture.md`. It extracts database mutation and Celery dispatch logic out of the FastAPI routers and into an agnostic Python service module, allowing both the API and the CLI to act as equal entry points.

###### 1. Service Layer Implementation
*   **Directive:** Abstract business logic away from the HTTP transport layer.
*   **Behavior:** 
    *   Create a new directory `src/services/` with an `__init__.py` and `job_service.py`.
    *   Move the logic that creates the `DummyImage`, commits to the database, and dispatches the `sleep_and_update_status` task out of the API and into a new function: `dispatch_dummy_job(db: Session) -> tuple[str, int]`. This function must return the `job_id` and `image.id`.

###### 2. API Refactoring (Thin Wrapper)
*   **Directive:** The FastAPI router must only handle HTTP concerns (parsing input, dependency injection, and Pydantic formatting).
*   **Behavior:** 
    *   Update `src/api/routes/jobs.py`. The `create_dummy_job` endpoint should now strictly call `job_service.dispatch_dummy_job(db)` and return the resulting data via the `JobDispatchResponse` Pydantic model. 

###### 3. CLI Formalization (diffpype-manage)
*   **Directive:** Elevate the CLI to a first-class administrative tool and add a command to trigger the dummy job directly.
*   **Behavior:** 
    *   Add a `[project.scripts]` section to `pyproject.toml` and define a command named `diffpype-manage` pointing to `src.cli:main`.
    *   Update `src/cli.py` to add a new `run-dummy` command alongside the existing `seed-db` command.
    *   The `run-dummy` command handler must instantiate its own database session (via `src.db.session.SessionLocal()`), call `job_service.dispatch_dummy_job(db)`, explicitly close the session, and print the resulting job ID to stdout.

###### 4. Test Suite Alignment
*   **Directive:** Ensure tests match the new boundaries.
*   **Behavior:** 
    *   Update `src/api/tests/test_jobs.py` to mock `src.services.job_service.dispatch_dummy_job` instead of the raw database session and Celery task.
    *   Add tests to `src/api/tests/test_cli.py` to verify the `run-dummy` command routes correctly and closes its database session.
    *   Create `src/services/tests/test_job_service.py` to test the newly isolated service function.

###### Logging
The "Logs" section will record Claude's work. Please use the following format:
###### (Short summary of the work)
###### (Short summary of the work)
...
###### Logs

###### Service Layer, Thin Router, diffpype-manage CLI, & Test Realignment
*   **Service Layer (§1):** Created `src/services/__init__.py` and `src/services/job_service.py`. The `dispatch_dummy_job(db: Session) -> tuple[str, int]` function encapsulates all business logic formerly in the router: creates `DummyImage(status=JobStatus.IN_PROCESS)`, commits to DB, dispatches `sleep_and_update_status.delay(image.id)`, stores the task ID on the row, and returns `(job_id, image_id)`. `src.services.job_service` added to `docs/index.rst` per CLAUDE.md Sphinx mandate.
*   **Thin Router (§2):** `src/api/routes/jobs.py` `create_dummy_job` endpoint reduced to two lines — calls `job_service.dispatch_dummy_job(db)` and wraps the result in `JobDispatchResponse`. All DB and Celery logic removed from the route layer.
*   **diffpype-manage CLI (§3):** `src/cli.py` updated: prog renamed to `diffpype-manage`, new `run-dummy` command added. `cmd_run_dummy` opens its own `SessionLocal()`, calls `job_service.dispatch_dummy_job(db)` inside a `try/finally` that guarantees `db.close()`, then prints `job_id` and `image_id`. `pyproject.toml` updated with `[project.scripts] diffpype-manage = "src.cli:main"` and a `[build-system]` (hatchling, `packages = ["src"]`). `uv lock` regenerated (57 packages, correct).
*   **Dockerfile Fix:** `docker/api.Dockerfile` and `docker/worker.Dockerfile` updated to a two-stage `uv sync` pattern — `uv sync --frozen --no-install-project` first (dep cache), then `COPY src`, then `uv sync --frozen` again (project install). This ensures hatchling finds `src/` when building the package, creating the `_editable_impl_diffpype.pth` file (`/app`) that makes `import src` work inside the entry-point script. Without this, hatchling built an empty wheel because `src/` was COPY'd after the first sync.
*   **Tests (§4):** `src/api/tests/test_jobs.py` POST test simplified — no longer mocks raw DB/Celery, instead patches `src.services.job_service.dispatch_dummy_job`. `src/api/tests/test_cli.py` extended to 9 tests: parser recognises `run-dummy`, routing dispatches to `cmd_run_dummy`, `cmd_run_dummy` calls `dispatch_dummy_job` with the session and closes it, output contains job_id. `src/services/tests/test_job_service.py` added with 3 tests: full commit/dispatch/return cycle, `IN_PROCESS` status set on created image, task ID stored as `latest_job_id`.
*   **Physical Verification:** `docker compose run --rm api diffpype-manage run-dummy` → `Dispatched dummy job. job_id=ff29dea4-cb17-4913-8ce6-bc6fb6e54eec, image_id=5`.
*   **Test Verification:** `pytest --cov=src --cov-fail-under=90` → **22 passed, 96.72% coverage**. `src/services/job_service.py` and `src/api/routes/jobs.py` at 100%.