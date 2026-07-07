##### 18: Observability, CLI Guide, and Architecture Wiki
**Version:** 0.2

###### Preamble
This document enhances system observability by adding explicit execution timestamps to domain entities and rendering their elapsed times in the UI and CLI. It also expands the Sphinx documentation engine to include a human-readable CLI guide and converts the architectural markdown files into a browsable static wiki.

###### 1. Database Timestamps (Observability)
*   **Directive:** Track both row-level provenance and explicit job execution timing on domain entities.
*   **Behavior:**
    *   In `src/db/models.py`, create a `TimestampMixin` class that provides `created_at` (defaulting to `func.now()`) and `updated_at` (defaulting to `func.now()` and updating on `onupdate=func.now()`) columns. Apply this mixin to `DummyImage` and `JobConfiguration`.
    *   To track actual job run times without overloading the `updated_at` semantic, add `job_started_at` (DateTime, nullable) and `job_finished_at` (DateTime, nullable) columns directly to the `DummyImage` model.
    *   Update `src/worker/tasks.py` and `base_task.py`. The worker must set `job_started_at = func.now()` right before the task begins, and `job_finished_at = func.now()` when the status transitions to COMPLETE or FAILED.
    *   Generate the Alembic migration for these column additions.

###### 2. Expose and Display Elapsed Times (API, UI, & CLI)
*   **Directive:** Bubble the explicit timestamps up to the API boundary and render the elapsed run times for the user.
*   **Behavior:**
    *   Update the `DummyImageStatus` Pydantic model in `src/api/schemas.py` and the corresponding TypeScript interface in `src/ui/src/api.ts` to include the nullable `created_at`, `job_started_at`, and `job_finished_at` datetimes.
    *   Update `src/ui/src/pages/DashboardPage.tsx` to calculate and display the elapsed "Run Time" (if started) or "Queue Time" (if pending) using standard JavaScript Date math.
    *   Update the CLI `get-dummy` command in `src/cli.py` to calculate and print these elapsed times alongside its ASCII table output.

###### 3. Human-Readable CLI Guide
*   **Directive:** Provide a tutorial-style guide for the DevOps CLI.
*   **Behavior:**
    *   Create a new file at `docs/cli_guide.rst`.
    *   Write human-readable documentation detailing how to use the `diffpype-manage` CLI, including explicit terminal examples for `seed-db`, `run-dummy`, `get-dummy`, and `reset-db`.
    *   Include this new file in the `toctree` of `docs/index.rst`.

###### 4. Architecture Wiki (MyST Parser)
*   **Directive:** Integrate the Architecture Decision Records (ADRs) into the Sphinx HTML build.
*   **Behavior:**
    *   Add `myst-parser` to `docs/sphinx_requirements.txt` and to the test dependency group in `pyproject.toml` so Sphinx can parse Markdown files.
    *   Update `docs/conf.py` to include `"myst_parser"` in the `extensions` list.
    *   Create a `docs/architecture/index.md` file that acts as a Table of Contents, linking to all the numbered markdown files in that directory.
    *   Include `architecture/index.md` in the `toctree` of `docs/index.rst` so the architecture rules are rendered as a browsable web page in the Sphinx output.

###### 5. Test Suite Alignment
*   **Directive:** Maintain 100% test coverage and zero Sphinx warnings.
*   **Behavior:**
    *   Update integration tests to verify the `created_at` and `updated_at` columns are populated.
    *   Run `sphinx-build -b html docs docs/_build/html -W` to guarantee the MyST parser correctly links the architecture files without warnings.

###### Logging
The "Logs" section will record Claude's work. Please use the following format:
###### (Short summary of the work)
###### (Short summary of the work)
...
###### Logs

###### Observability Timestamps, Elapsed-Time Display, CLI Guide & MyST Architecture Wiki
*   **§1 Database Timestamps:** Added a `TimestampMixin` to `src/db/models.py` providing `created_at` and `updated_at` (both `DateTime(timezone=True)`, `server_default=func.now()`, `updated_at` also `onupdate=func.now()`), applied to `DummyImage` and `JobConfiguration`. Added nullable `job_started_at` / `job_finished_at` columns to `DummyImage` for explicit run timing (kept distinct from `updated_at`). `src/worker/tasks.py::sleep_and_update_status` now stamps `job_started_at = func.now()` in its own short transaction **before** the sleep (so no DB connection is held across the sleep, and a mid-run crash is recoverable), then stamps `job_finished_at` alongside the `COMPLETE` transition. `src/worker/base_task.py::DiffpypeTask.on_failure` stamps `job_finished_at` when transitioning to `FAILED`.
*   **Migration (0004):** `docker compose exec` is blocked in this sandbox, so autogenerate could not be run here; authored `20260707_0004_add_observability_timestamps.py` manually to match the model diff exactly (revision `0004`, down_revision `0003`). Adds `created_at`/`updated_at` (with `server_default=text("now()")` so existing rows backfill and the NOT NULL holds) to both tables, plus nullable `job_started_at`/`job_finished_at` on `dummy_images`; `downgrade` drops all six.
*   **§2 Elapsed Times (API/UI/CLI):** Added `created_at`, `job_started_at`, `job_finished_at` (nullable datetimes) to `DummyImageStatus` in `src/api/schemas.py` and to the `DummyImageStatus` TS interface in `src/ui/src/api.ts`. `DashboardPage.tsx` gained `formatDuration` + `elapsedLabel` helpers rendering **Run Time** (once started; live-updates while running via the existing 1 s poll, freezes at `job_finished_at`) or **Queue Time** (while pending) via JS `Date` math. The CLI `get-dummy` command gained a mirrored `_elapsed_label` helper (Python `datetime`, tz-aware) printed beneath the ASCII table.
*   **§3 CLI Guide:** Created `docs/cli_guide.rst` — a tutorial with terminal examples for `seed-db`, `run-dummy`, `get-dummy`, and `reset-db` — and added it to a new `toctree` in `docs/index.rst`.
*   **§4 Architecture Wiki (MyST):** Added `myst-parser==4.0.0` to `docs/sphinx_requirements.txt` and the `test` dependency group (`uv lock`); registered `"myst_parser"` in `docs/conf.py` extensions. Created `docs/architecture/index.md` (MyST `{toctree}` over all numbered ADRs) and linked it from `docs/index.rst`. Because the ADRs intentionally begin at an H5/H6 heading convention, added `suppress_warnings = ["myst.header"]` so a `-W` build stays meaningful for every other warning class; excluded the out-of-scope `prd.md` from the source tree to avoid an orphan-page warning.
*   **§5 Tests:** Added integration tests asserting `created_at`/`updated_at` populate on both tables (and job-timing columns start null). Updated worker tests: completion test now asserts the two-transaction flow and both timestamps (via a patched `func.now`), plus a new regression test proving `job_started_at` is committed **before** the sleep; `on_failure` test asserts `job_finished_at`. Updated the API GET test and CLI serializer tests for the three new schema fields, and added `_elapsed_label` tests (finished Run Time, running Run Time, Queue Time, none) plus a `get-dummy` elapsed-output test.
*   **Verification:** `pytest --ignore=src/db/tests -q` → **62 passed**; all new code at 100% coverage (`src/cli.py` sole miss is the `if __name__ == "__main__"` guard). `sphinx-build -b html docs docs/_build/html -W` → **build succeeded, 0 warnings** (18 ADRs + CLI guide now rendered). Integration tests (`src/db/tests`) run in Docker where the live DB is reachable.
*   **Action Required (human):** Rebuild the `api` and `worker` images (models, migration `0004`, worker timing logic, and schema changes must be baked in), then apply the migration and restart workers:
    *   `docker compose build api worker_light worker_heavy`
    *   `docker compose up -d api` then `docker compose exec api alembic upgrade head` → should report `0004 (head)`
    *   `docker compose restart worker_light worker_heavy` to clear stale in-memory task code.
*   **Git Workflow:** All changes on `feature/observability_and_docs`; to be merged via Pull Request against `main`.
*   **Reminder:** This was an Opus task — revert to the standard (Sonnet) model for routine follow-up work.