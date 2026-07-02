### 06: API & Worker Logic Refactoring
**Version:** 0.1

##### Preamble
This document dictates the structural refactoring of the FastAPI entry points and the Celery worker routing. It establishes the `APIRouter` pattern to prevent monolithic API files, delegates database initialization to Alembic, and defines the core system enumerations for task and queue routing.

##### 1. Fiducial Enumerations
*   **Directive:** Establish the core enumerations for the system state and worker routing in the database layer (e.g., `src/db/models.py` or a dedicated `src/db/enums.py`), so they can be consumed by FastAPI, SQLAlchemy, and Celery.
*   **Status Enum:** Implement a status enumeration with the following fiducial states: `pending`, `in_process`, `complete`, and `failed`.
*   **Queue Enum:** Implement a queue enumeration representing the hardware routing tiers: `light`, `heavy_memory`, and `gpu`.

##### 2. API Routing (APIRouter)
*   **Directive:** Deprecate the single monolithic `main.py` controller.
*   **Behavior:** Implement FastAPI's `APIRouter` pattern. Scaffold a new directory for route controllers (e.g., `src/api/routes/`). Move the existing Stage 0 job endpoints into a dedicated `jobs.py` router file, and include this router in the core `main.py` application. 

##### 3. Application Lifespan & DB Initialization
*   **Directive:** Remove database table creation from the FastAPI boot sequence.
*   **Behavior:** Delete the `init_db()` execution from the `lifespan` context manager in `src/api/main.py`. Because the application now relies strictly on Alembic migrations (as defined in Document 05), the API should assume the database schema is already fully materialized before the server starts.

##### 4. Worker Routing
*   **Directive:** Define the queues but temporarily route all tasks to the `light` queue.
*   **Behavior:** Update the Celery app configuration (`src/worker/celery_app.py`) to recognize the `light`, `heavy_memory`, and `gpu` queues using the new Enum. However, until the heavy Python domain logic is ported over from the prototype, explicitly route the Stage 0 dummy tasks to the `light` queue. This prevents the need to provision and run separate `gpu` or `heavy_memory` Celery workers locally right now.

#### Logging
The "Logs" section will record Claude's work. Please use the following format:
##### (Short summary of the work)
##### (Short summary of the work)
...
#### Logs

##### Enum Refactor, APIRouter Pattern, Lifespan Cleanup, & Worker Routing
*   **Fiducial Enumerations:** Replaced `DummyImageStatus` with `JobStatus(str, enum.Enum)` using fiducial values `pending/in_process/complete/failed`. Removed `external` from `CeleryQueue`, leaving `light/heavy_memory/gpu`. Updated `src/db/models.py` (both mapped columns), `src/worker/tasks.py` (assigns `JobStatus.COMPLETE`), and the initial Alembic migration (enum type names updated: `dummy_image_status` → `job_status`; values match new enum; `external` removed from `celery_queue`). Updated worker test renamed to `test_sleep_and_update_status_marks_image_complete`.
*   **APIRouter:** Created `src/api/routes/__init__.py` and `src/api/routes/jobs.py`. Moved `POST /jobs/dummy` and `GET /jobs/dummy/{image_id}` into a dedicated `APIRouter(prefix="/jobs")`. `src/api/main.py` reduced to 6 lines: app instantiation, CORS middleware, and `app.include_router(jobs_router)`. All endpoint tests updated to patch `src.api.routes.jobs.sleep_and_update_status.delay` (new module path).
*   **Lifespan Removal:** Removed the lifespan context manager from `main.py` entirely — no DB init, no seeding at startup. The API now assumes Alembic has already materialized the schema (run by CI before pytest and by the developer before `docker compose up`). `src/api/tests/conftest.py` cleared (no startup mocks needed).
*   **Worker Routing:** `src/worker/celery_app.py` updated to import `CeleryQueue` and use `CeleryQueue.LIGHT` in `task_routes`, routing `sleep_and_update_status` to the `light` queue.
*   **Verification:** `docker compose build api` succeeded. `pytest --cov=src --cov-fail-under=90` → 4 passed, 90.51% coverage. `src/api/main.py` and `src/api/routes/jobs.py` both at 100% coverage.
