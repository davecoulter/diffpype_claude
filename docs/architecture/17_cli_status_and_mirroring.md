##### 17: CLI API Mirroring & Status Tables
**Version:** 0.1

###### Preamble
This document extracts the dummy job status polling into the Shared Service Layer and implements a human-readable ASCII table output for the CLI, ensuring strict parity between the API and CLI boundaries.

###### 1. Service Layer Extraction
*   **Directive:** Abstract the status polling logic out of the FastAPI router.
*   **Behavior:**
    *   In `src/services/job_service.py`, create a `get_dummy_job(db: Session, image_id: int) -> DummyImage | None` function.
    *   Update `src/api/routes/jobs.py` to call this service function instead of querying `db.get(DummyImage, image_id)` directly.

###### 2. ASCII Table Formatting
*   **Directive:** CLI outputs for domain entities must be formatted as human-readable ASCII tables.
*   **Behavior:**
    *   Add the `tabulate` package to `pyproject.toml`.
    *   Create a utility function in `src/cli.py` to safely serialize database entities or Pydantic models into a list of dictionaries and print them using `tabulate(..., headers="keys", tablefmt="grid")`.

###### 3. CLI `get-dummy` Command
*   **Directive:** Implement the API mirror command for status polling.
*   **Behavior:**
    *   In `src/cli.py`, add a `get-dummy` command that accepts an `--id` integer argument.
    *   The handler must open a database session, call `job_service.get_dummy_job`, and print the resulting entity using the `tabulate` ASCII formatter. If the image is not found, print a clear 404-style error message to stdout.

###### 4. Test Suite Alignment
*   **Directive:** Maintain 100% test coverage.
*   **Behavior:**
    *   Update `src/api/tests/test_jobs.py` to mock the new service function.
    *   Add tests for the `get-dummy` command in `src/api/tests/test_cli.py`.
    *   Add tests for the new fetch function in `src/services/tests/test_job_service.py`.

###### Logging
The "Logs" section will record Claude's work. Please use the following format:
###### (Short summary of the work)
###### (Short summary of the work)
...
###### Logs

###### Service Extraction, ASCII Table Formatter, get-dummy CLI Command & Test Suite
*   **§1 Service Layer Extraction:** Added `get_dummy_job(db: Session, image_id: int) -> DummyImage | None` to `src/services/job_service.py` — a thin wrapper around `db.get(DummyImage, image_id)`. Refactored `src/api/routes/jobs.py` `GET /jobs/dummy/{image_id}` to delegate to this function instead of calling `db.get` directly; removed the now-unused `DummyImage` import from the route module. This is the first exercise of the API/CLI Parity rule: both boundaries now call the exact same service function.
*   **§2 ASCII Table Formatting:** Added `tabulate==0.9.0` to `pyproject.toml` (`uv lock` → 60 packages). Added two helpers to `src/cli.py`: `_entity_to_dict(entity)` — duck-types on `model_dump` for Pydantic models, falls back to `{col.name: getattr(entity, col.name) for col in entity.__table__.columns}` for SQLAlchemy ORM objects; `_print_entity_table(entities: list)` — serializes each entity via `_entity_to_dict` and prints with `tabulate(..., headers="keys", tablefmt="grid")`. Both use lazy imports.
*   **§3 CLI `get-dummy` Command:** Added `cmd_get_dummy(args)` to `src/cli.py`. Opens a `SessionLocal`, calls `job_service.get_dummy_job(db, args.id)`, closes the session in `finally`, then either prints the ASCII table (found) or a clear `"Error: No DummyImage found with id=N."` message (not found). Registered `get-dummy` subparser with a required `--id INT` argument; wired into `main()`.
*   **§4 Test Suite Alignment:** Updated `src/api/tests/test_jobs.py` GET tests to mock `src.services.job_service.get_dummy_job` (previously mocked `mock_db.get` directly — now correctly tests the route's delegation to the service). Added 2 service tests to `src/services/tests/test_job_service.py` (found/not-found cases). Added 8 tests to `src/api/tests/test_cli.py`: `_entity_to_dict` for ORM object and Pydantic model, `_print_entity_table` stdout output, parser recognition, `main()` routing, `cmd_get_dummy` table output, error message, and session-close guarantee.
*   **Verification:** `pytest --ignore=src/db/tests -q` → **56 passed, 11 new tests** (all new code at 100% coverage). `sphinx-build -b html docs docs/_build/html -W` → **build succeeded, 0 warnings**. Full suite with integration tests: `docker compose exec api uv run pytest --cov=src --cov-fail-under=90`.
*   **Git Workflow:** All changes on `feature/cli_status_mirroring`; to be merged via Pull Request against `main`.

###### api Image Rebuild for tabulate
*   **Issue:** Integration test run inside Docker failed with `ModuleNotFoundError: No module named 'tabulate'` on the two tests that exercise `_print_entity_table` and `cmd_get_dummy`. Root cause: the api image was baked before `tabulate==0.9.0` was added to `pyproject.toml`, so the installed venv inside the container didn't include it.
*   **Fix:** Ran `docker compose build api` (deps layer cache-busted by `pyproject.toml`/`uv.lock` change; `tabulate==0.9.0` confirmed installed in build log) then `docker compose up -d api`.