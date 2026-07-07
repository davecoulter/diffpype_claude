##### 16: Generalized CLI Execution Strategy
**Version:** 0.1

###### Preamble
This document defines the generalized worker strategy for executing external astronomical CLI tools (like HOTPANTS) via Celery. It leverages the `JobConfiguration` table to dynamically construct commands, execute them securely without shell injection vulnerabilities, and guarantee provenance by saving the exact command string back to the database.

###### 1. CLI Command Builder Utility
*   **Directive:** Safely translate Pydantic-validated JSON payloads into flat shell command lists suitable for `subprocess`.
*   **Behavior:** 
    *   Create a new utility module (e.g., `src/worker/utils.py`).
    *   Implement a function `build_cli_command(executable: str, kwargs: dict) -> list[str]`.
    *   It must take the executable name and a dictionary of arguments and flatten them into a list, prepending a hyphen to the keys (e.g., `{"inim": "sci.fits", "c": "t"}` becomes `["executable", "-inim", "sci.fits", "-c", "t"]`).

###### 2. Generic Execution Task
*   **Directive:** Implement a Celery task that executes external shell commands based on database state.
*   **Behavior:**
    *   In `src/worker/tasks.py`, create a new task named `execute_cli_tool(job_config_id: int, executable: str, correlation_id: str | None = None)`.
    *   The task must inherit from `DiffpypeTask` (so exceptions are safely handled by the boundary pattern).
    *   The task must fetch the `JobConfiguration` record from the database using `job_config_id`.
    *   Extract the `job_kwargs` dictionary and pass it to `build_cli_command`.
    *   Save the joined command string (e.g., `" ".join(cmd_list)`) back to `JobConfiguration.execution_command` and `db.commit()`.
    *   Execute the command using `subprocess.run(cmd_list, capture_output=True, text=True, check=True)`.
    *   Log the standard output via `structlog`.

###### 3. Test Suite Alignment
*   **Directive:** Maintain 100% test coverage and ensure the `subprocess` boundary is fully mocked.
*   **Behavior:**
    *   Add tests for `build_cli_command` to verify proper argument flattening.
    *   Add tests for `execute_cli_tool` in `src/worker/tests/test_tasks.py`. Use `pytest-mock` to mock `subprocess.run` and the database session, specifically verifying that the correct list is passed to `subprocess.run` and that the `execution_command` is successfully assigned to the mocked database entity.

###### Logging
The "Logs" section will record Claude's work. Please use the following format:
###### (Short summary of the work)
###### (Short summary of the work)
...
###### Logs

###### CLI Command Builder, Generic Execution Task, & Test Suite Alignment
*   **§1 CLI Command Builder:** Created `src/worker/utils.py` with a single `build_cli_command(executable: str, kwargs: dict) -> list[str]` function. It prepends `executable` and flattens each key–value pair as `["-key", str(value)]`, yielding a `subprocess`-safe list (e.g., `{"inim": "sci.fits", "c": "t"}` → `["hotpants", "-inim", "sci.fits", "-c", "t"]`). Insertion order is preserved (Python 3.7+ dicts); values are coerced to `str` to support numeric kwargs from JSON payloads.
*   **§2 Generic Execution Task:** Added `execute_cli_tool(job_config_id: int, executable: str, correlation_id: str | None = None)` to `src/worker/tasks.py`. Inherits from `DiffpypeTask` (rollback-safe `on_failure` boundary). Flow: bind correlation ID → fetch `JobConfiguration` → call `build_cli_command` → write `execution_command = " ".join(cmd_list)` back to `JobConfiguration` → `db.commit()` → `subprocess.run(cmd_list, capture_output=True, text=True, check=True)` → log stdout. **Not registered in `task_routes`** — queue is chosen by the caller at dispatch time via `.apply_async(queue=...)`, since the same generic task may run lightweight or memory-intensive tools depending on context.
*   **§3 Test Suite Alignment:** Added `src/worker/tests/test_utils.py` (4 tests: empty kwargs, kwarg flattening, numeric coercion, insertion order). Extended `src/worker/tests/test_tasks.py` with 4 tests for `execute_cli_tool`: verifies `subprocess.run` receives the correct list, confirms `execution_command` is assigned and committed, asserts session closes on `CalledProcessError`, and validates `None` job_kwargs falls back to executable-only command. All mocks patch `src.worker.tasks.subprocess.run` and `src.worker.tasks.SessionLocal` directly — no real subprocess or DB calls. Added `src.worker.utils` to `docs/index.rst`; Sphinx docstring mandate satisfied with single-sentence docstrings on all new symbols.
*   **Verification:** `pytest --ignore=src/db/tests -q` → **45 passed** (8 new tests; all new modules at 100% coverage; existing tests unaffected). `sphinx-build -b html docs docs/_build/html -W` → **build succeeded, 0 warnings**. Full suite with integration tests requires Docker (`docker compose exec api uv run pytest`) where 90%+ coverage is maintained.
*   **Git Workflow:** All changes on `feature/stage0-polish`; to be merged via Pull Request against `main`.

###### CLI Correlation ID Bug Fix & .gitignore Housekeeping
*   **Bug: Missing correlation ID on CLI dispatch.** When `diffpype-manage run-dummy` was invoked, Celery and worker logs showed no `correlation_id` because only the HTTP middleware in `src/api/main.py` generated one. The CLI path had no equivalent. Fixed in `src/cli.py`: `cmd_run_dummy` now calls `clear_contextvars()`, generates `str(uuid.uuid4())`, and calls `bind_contextvars(correlation_id=...)` before delegating to `job_service.dispatch_dummy_job`. The service picks it up via `get_contextvars()` and forwards it to the Celery task as a kwarg, so the correlation ID now threads through CLI → service → worker logs identically to the HTTP path. The correlation ID is also printed to stdout for human cross-referencing. Regression test added to `src/api/tests/test_cli.py` (`test_cmd_run_dummy_binds_a_valid_uuid_correlation_id`): calls `cmd_run_dummy` then asserts `get_contextvars()["correlation_id"]` parses as a valid `uuid.UUID`.
*   **Housekeeping:** Added `.coverage` and `htmlcov/` to `.gitignore` — these are pytest-cov artifacts generated by local `uv run pytest` runs and should never be committed.