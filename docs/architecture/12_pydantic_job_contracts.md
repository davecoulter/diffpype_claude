##### 12: Pydantic Job Contracts (Polymorphic Configuration)
**Version:** 0.1

###### Preamble
This document establishes strict type-safety for job configurations entering the system. Because Diffpype will handle diverse tools (e.g., HOTPANTS, JWST Pipeline), the API must validate tool-specific parameters before persisting them to the flexible `JSONB` database column. This is achieved using Pydantic Discriminated Unions.

###### 1. Strict Configuration Schemas
*   **Directive:** Define strict Pydantic models for specific pipeline tasks.
*   **Behavior:** 
    *   In `src/api/schemas.py`, create a base class `BaseJobConfig(BaseModel)`.
    *   Create a `DummyJobConfig(BaseJobConfig)` model with a single field `sleep_duration: int = Field(default=5, ge=1, le=10)`.
    *   (Future stages will add `HotpantsConfig`, `JwstMosaicConfig`, etc. here).

###### 2. Polymorphic Job Submission
*   **Directive:** The API payload must enforce validation based on the requested task.
*   **Behavior:** 
    *   Update `src/api/schemas.py` to define a `JobSubmitRequest` model.
    *   It must contain `task_name: str` and `config: DummyJobConfig` (eventually a union of all config models, discriminated by `task_name`).

###### 3. Service Layer and DB Integration
*   **Directive:** The validated configuration must be persisted and passed to Celery.
*   **Behavior:** 
    *   Update `src/db/models.py`. Add a `job_kwargs` column (using SQLAlchemy's `JSON` or native `JSONB`) to the `DummyImage` table to act as our prototype configuration storage.
    *   Update `src/services/job_service.py` (`dispatch_dummy_job`). It must now accept the validated `config` dictionary, save it to the new `job_kwargs` column, and pass the configuration parameters to the Celery task.
    *   Update the Celery task in `src/worker/tasks.py` to accept the `sleep_duration` argument and sleep for that duration instead of the hardcoded 5 seconds.

###### 4. CLI Alignment
*   **Directive:** The CLI must construct the proper JSON payload and route it through the service layer.
*   **Behavior:** 
    *   Update `src/cli.py` (`run-dummy` command) to accept an optional `--sleep` argument. Construct a dictionary matching the `JobSubmitRequest` schema and pass it to the service layer.

###### 5. Test Suite Alignment
*   **Directive:** Ensure tests match the new data contracts and maintain 100% coverage.
*   **Behavior:** 
    *   Update API tests to pass the new JSON payload structure.
    *   Verify that passing a `sleep_duration` of `11` correctly throws a Pydantic 422 Validation Error.
    *   Update the `conftest.py` migrations as needed to reflect the new `job_kwargs` column, or generate a new Alembic migration for it.

###### Logging
The "Logs" section will record Claude's work. Please use the following format:
###### (Short summary of the work)
###### (Short summary of the work)
...
###### Logs

###### Pydantic Job Contracts, job_kwargs Column, & Full Test Alignment
*   **Strict Configuration Schemas (§1):** Added to `src/api/schemas.py`: `BaseJobConfig(BaseModel)` (empty base for future extension); `DummyJobConfig(BaseJobConfig)` with `sleep_duration: int = Field(default=5, ge=1, le=10)` enforcing the 1–10 range at the Pydantic layer; `JobSubmitRequest(BaseModel)` with `task_name: str` and `config: DummyJobConfig`. `Field` imported from `pydantic`.
*   **Database Migration (§3 — schema first):** Created `migrations/versions/20260702_0002_add_job_kwargs_to_dummy_images.py` (`revision=0002`, `down_revision=0001`). `upgrade()` adds `job_kwargs sa.JSON() nullable=True` to `dummy_images`; `downgrade()` drops it. `alembic upgrade head` applied successfully (`0002 (head)` confirmed).
*   **Model Update:** Added `job_kwargs: Mapped[dict | None] = mapped_column(sa.JSON, nullable=True)` to `DummyImage` in `src/db/models.py`.
*   **Service Layer (§3):** `dispatch_dummy_job(db, config: dict)` now accepts the validated config dict, passes `job_kwargs=config` to the `DummyImage` constructor, and passes `config["sleep_duration"]` as the second argument to `sleep_and_update_status.delay(image.id, sleep_duration)`.
*   **API Router (§2):** `create_dummy_job` endpoint now accepts `body: JobSubmitRequest` as a request body and calls `job_service.dispatch_dummy_job(db, body.config.model_dump())`. Pydantic blocks invalid `sleep_duration` values at the HTTP boundary with a `422 Unprocessable Entity` before the service is ever called.
*   **Celery Task (§3):** `sleep_and_update_status(image_id, sleep_duration: int = 5)` now sleeps for the caller-supplied duration instead of the hardcoded 5 seconds.
*   **CLI Alignment (§4):** `cmd_run_dummy` parameter renamed from `_` back to `args` (now reads `args.sleep`). `run-dummy` subparser gets `--sleep SECONDS` (type=int, default=5). Config dict `{"sleep_duration": args.sleep}` is passed to the service.
*   **Test Suite (§5):**
    - `test_jobs.py`: POST test updated with `VALID_PAYLOAD = {"task_name": "dummy_sleep", "config": {"sleep_duration": 5}}`. Two new 422 tests: `sleep_duration=11` (above max) and `sleep_duration=0` (below min).
    - `test_job_service.py`: All 5 tests now pass `CONFIG = {"sleep_duration": 5}` to `dispatch_dummy_job`. `mock_delay.assert_called_once_with(99, 5)` verifies `sleep_duration` is forwarded. New `test_dispatch_dummy_job_stores_config_in_job_kwargs` and `test_dispatch_dummy_job_passes_sleep_duration_to_task`.
    - `test_tasks.py`: Updated to call `sleep_and_update_status(42, 3)` and assert `mock_sleep.assert_called_once_with(3)`. New `test_sleep_and_update_status_uses_default_sleep_duration` verifies the `default=5` fallback.
    - `test_integration.py`: Two new tests — `test_dummy_image_job_kwargs_roundtrip` (stores and retrieves `{"sleep_duration": 7}`) and `test_dummy_image_job_kwargs_nullable` (verifies default `None`).
    - `test_cli.py`: `test_parser_recognises_run_dummy_command` now asserts `args.sleep == 5`. New `test_run_dummy_accepts_custom_sleep_arg`. Dispatch assertion updated to `assert_called_once_with(mock_session, {"sleep_duration": 3})`.
*   **Verification:** `alembic upgrade head` → `0002 (head)`. `pytest --cov=src --cov-fail-under=90` → **30 passed, 98.10% coverage**. `src/db/session.py` reached 100% (integration tests now exercise the `get_db` generator via the test DB session).

###### Fix: UI Payload 422 Error
*   `src/ui/src/api.ts` `createDummyJob` updated to send the correct polymorphic JSON payload (`{"task_name": "dummy_sleep", "config": {"sleep_duration": 5}}`) with a `Content-Type: application/json` header. Without this body, `POST /jobs/dummy` was returning 422 because `JobSubmitRequest` is now a required Pydantic model.

###### Fix: Worker TypeError & Infinite UI Poll on Task Failure
*   **Root cause — TypeError:** The `worker` service was an orphan container from before doc 10 split it into `worker_light`/`worker_heavy`. It had loaded the old `sleep_and_update_status(image_id)` signature at startup and cached it in memory. The new API was calling `.delay(image.id, sleep_duration)` with two positional arguments, causing `TypeError: takes 1 positional argument but 2 were given`. Fix: `docker compose up -d --remove-orphans` stopped and removed the orphan, built and started the correct `worker_light` and `worker_heavy` containers with the updated signature.
*   **Root cause — infinite poll:** If any exception occurred inside `sleep_and_update_status` (e.g. a DB timeout or the `TypeError` above), the `finally: db.close()` block ran without committing, leaving `DummyImage.status` stuck at `"in_process"` in Postgres indefinitely. The React frontend polls on a 1-second `refetchInterval` that only stops when status is `"complete"` or `"failed"` — so a stuck `"in_process"` causes infinite polling with no error indicator.
*   **Fix in `src/worker/tasks.py`:** Restructured the task to open the `SessionLocal` before the `try` block so the same session is available in the exception handler. An `except Exception` block now: (1) calls `db.rollback()` to clear dirty state, (2) re-fetches the image and sets `status = JobStatus.FAILED`, (3) commits — so the UI poll terminates with a red indicator. A nested `try/except` around the failure write silently swallows any secondary error (e.g. the DB itself is gone) so the session can still be closed cleanly. A bare `raise` re-raises the original exception so Celery marks the task FAILED in Redis and Flower logs the full stack trace.
*   **New tests (4 total in `test_tasks.py`):** `test_sleep_and_update_status_writes_failed_on_exception` verifies `db.rollback()` is called, `image.status` becomes `FAILED`, and `db.commit()` is called exactly once. `test_sleep_and_update_status_reraises_after_failed_write` verifies the original exception is re-raised even when the failure-write itself errors. Full suite: **32 passed, 98.23% coverage**. `src/worker/tasks.py` at 100%.