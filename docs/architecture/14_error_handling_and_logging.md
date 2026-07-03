##### 14: Error Handling & Structured Logging
**Version:** 0.2

###### Preamble
This document formalizes the global logging, trace threading, and exception-bubbling strategy for the Diffpype system. It enforces two strict error-handling patterns:
1. **The Domain Exception Pattern (Business Logic):** The `src/services/` layer must raise specific, anticipated exceptions for known failure states.
2. **The Boundary Pattern (Framework Backstop):** Global exception handlers at the FastAPI and Celery outer boundaries catch anything that bubbles up, logging the crash and ensuring stable infrastructure recovery.

###### 1. Structured Logging & Correlation IDs (`structlog`)
*   **Directive:** All system components must stream JSON logs to `stdout` via `structlog`, threaded by a correlation ID.
*   **Behavior:** 
    *   Add `structlog` to `pyproject.toml`. Create `src/core/logger.py` to configure it.
    *   **FastAPI:** Implement a middleware that generates a `correlation_id` (UUID) for incoming requests and binds it to the logger.
    *   **Celery:** Pass the `correlation_id` into the task dispatch (e.g., inside `job_kwargs`) so the worker can bind the exact same ID to its own `structlog` context before executing.

###### 2. Framework Boundary Pattern: Celery Global Error Handling
*   **Directive:** Celery tasks must never silently fail or leave database records in an orphaned state.
*   **Behavior:**
    *   Create `DiffpypeTask(celery.Task)` in a new file (e.g., `src/worker/base_task.py`).
    *   Override the `on_failure` method to log the exception via `structlog`.
    *   **Transaction Safety:** The handler MUST explicitly call `db.rollback()` to clear the invalid transaction state before transitioning the database entity to `JobStatus.FAILED`.
    *   Refactor `src/worker/tasks.py` (`sleep_and_update_status`) to inherit from this base task.

###### 3. Framework Boundary Pattern: FastAPI Global Catch-All
*   **Directive:** The API must bubble up unexpected errors cleanly.
*   **Behavior:**
    *   In `src/api/main.py`, implement `@app.exception_handler(Exception)`.
    *   It must log the full traceback via `structlog` and return a standard HTTP 500 JSON response.

###### 4. Domain Exception Pattern & Audit
*   **Directive:** Audit and refactor the existing codebase to conform to the dual-pattern strategy.
*   **Behavior:**
    *   Remove the manual `try/except` block currently inside `sleep_and_update_status`.
    *   Audit the framework and business logic layers (API routes, services). Remove raw `print()` statements and convert them to `structlog`.

###### Logging
The "Logs" section will record Claude's work. Please use the following format:
###### (Short summary of the work)
###### (Short summary of the work)
...
###### Logs

###### structlog Configuration, Correlation IDs, DiffpypeTask Boundary, & FastAPI Backstop
*   **Structured Logging (§1):** Added `structlog==24.4.0` to `pyproject.toml` (`uv lock` → 58 packages). Created `src/core/__init__.py` and `src/core/logger.py`. `configure_logging()` sets a processor chain — `merge_contextvars` → `add_log_level` → ISO `TimeStamper` → `StackInfoRenderer` → `format_exc_info` → `JSONRenderer` — with `PrintLoggerFactory` (stdout) and `make_filtering_bound_logger(INFO)`. Idempotent; called at module load in `src/api/main.py` (API process) and `src/worker/celery_app.py` (worker process, and transitively any CLI path that imports the service/task layer) so every component streams JSON — verified live: the worker emits `{"event": "task_started", ...}` / `{"event": "task_completed", ...}` and the service emits `{"event": "dummy_job_dispatched", ...}`. `get_logger()` returns a contextvar-bound logger.
*   **Correlation IDs (§1):** `src/api/main.py` `@app.middleware("http")` clears contextvars, generates a UUID `correlation_id`, binds it via `structlog.contextvars.bind_contextvars`, and echoes it back as the `X-Correlation-ID` response header. Because `contextvars` do **not** survive the process-fork boundary into the Celery worker, `src/services/job_service.dispatch_dummy_job` reads the active ID via `get_contextvars().get("correlation_id")` and forwards it explicitly as a `.delay(..., correlation_id=...)` keyword argument. The task re-binds it with `bind_contextvars` at the top of its body so worker logs carry the same ID. CLI-originated jobs simply pass `correlation_id=None`.
*   **Celery Boundary Pattern (§2):** Created `src/worker/base_task.py` with `DiffpypeTask(celery.Task)`. `on_failure(self, exc, task_id, args, kwargs, einfo)` extracts `image_id = args[0]`, re-binds the correlation ID if present, logs a structured `task_failed` event (with `exc_info=einfo`), then opens a **fresh** `SessionLocal`, calls `db.rollback()` to clear any invalid transaction state, transitions the entity to `JobStatus.FAILED`, commits, and closes in a `finally`. `src/worker/tasks.py` now declares `@celery_app.task(base=DiffpypeTask, ...)` and the manual `try/except` from the previous fix was **removed** — the task body is now linear (`bind → log → sleep → commit COMPLETE → log`); any exception propagates to Celery, which invokes `on_failure`.
*   **FastAPI Backstop (§3):** `@app.exception_handler(Exception)` logs the full traceback (`exc_info=exc`) via structlog and returns a stable `HTTP 500 {"detail": "Internal Server Error"}` JSON response.
*   **Audit (§4):** Grep of `src/**/*.py` (excluding tests) for `print(` / `logging` found the only `print()` calls in `src/cli.py` — the human-facing DevOps CLI handlers, intentionally retained per the agreed design. No `logging`-module usage existed. Framework/business layers were already print-free; structlog instrumentation (`task_started`, `task_completed`, `dummy_job_dispatched`, `task_failed`, `unhandled_exception`) was added as positive logging.
*   **Test Isolation:** Added `src/conftest.py` with an autouse fixture that clears structlog contextvars before and after every test to prevent correlation-ID leakage across tests.
*   **Tests:** `test_tasks.py` rewritten (happy path, default sleep, and a new test proving exceptions now **propagate** and still close the session — no swallowing). New `test_base_task.py` (3 tests: rollback + FAILED + commit + close; missing image; empty args). New `test_main.py` (X-Correlation-ID header is a valid UUID; unhandled exception → 500; logger smoke test). Service tests updated to assert `correlation_id` is forwarded (both `None` and a bound value).
*   **Sphinx:** `src.core.logger` and `src.worker.base_task` added to `docs/index.rst`; `structlog` added to `autodoc_mock_imports` in `conf.py`.
*   **Verification:** `alembic upgrade head` → `0002 (head)` (no schema change this doc). `pytest --cov=src --cov-fail-under=90` → **42 passed, 98.66% coverage** (all new modules at 100%). `sphinx-build ... -W` → **build succeeded, 0 warnings**.