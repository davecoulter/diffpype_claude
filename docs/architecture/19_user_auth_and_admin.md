##### 19: User Authentication, Projects & SQLAdmin
**Version:** 0.3

###### Preamble
This document establishes the underlying User and Project data models to ensure strict job provenance. It extends auditing (timestamps and ownership) to all domain tables and integrates SQLAdmin to provide a lightweight CRUD dashboard.
*Note: The development database has been intentionally wiped and reset prior to this stage to allow for strict, non-nullable Foreign Key constraints without requiring complex backfill migrations.*

###### 1. Core Ownership Models (User & Project)
*   **Directive:** Establish the foundation for multi-user authentication and project grouping.
*   **Behavior:**
    *   In `src/db/models.py`, create a `User` model (with `id`, `username`, `email`, and `is_active` boolean).
    *   Create a `Project` model (with `id`, `name`, and `description`).
    *   Both models must inherit from the `TimestampMixin`.

###### 2. Provenance & Auditing
*   **Directive:** Ensure all database entities are tracked temporally and tied to a specific user.
*   **Behavior:**
    *   Apply the `TimestampMixin` to the `StepDefinition` model.
    *   Add a `user_id` ForeignKey column (`nullable=False`) to `Project`, `JobConfiguration`, and `StepDefinition`.
    *   Establish the bidirectional SQLAlchemy `relationship()` properties between `User` and these three models.
    *   Generate the Alembic migration for these additions.

###### 3. Auto-Seeding the Sysadmin
*   **Directive:** The system must provision a default identity to own foundational records.
*   **Behavior:**
    *   Update `src/db/seed.py`. The `seed_step_definitions()` function must first query for a default user (e.g., `username="sysadmin"`, `email="admin@diffpype.local"`, `is_active=True`). If it does not exist, create it.
    *   Assign this sysadmin's `id` to the `user_id` field of the dummy `StepDefinition` record when inserting it into the database.

###### 4. SQLAdmin Integration
*   **Directive:** Provide a web-based administrative GUI to easily inspect and modify the database.
*   **Behavior:**
    *   Add `sqladmin` and `itsdangerous` to `pyproject.toml`.
    *   Create a new module `src/api/admin.py`. Define SQLAdmin `ModelView` classes for `User`, `Project`, `StepDefinition`, `DummyImage`, and `JobConfiguration`.
    *   In `src/api/main.py`, instantiate the `Admin` object attached to the FastAPI `app` and the SQLAlchemy `engine`, and register all the model views. The dashboard should mount at `/admin`.

###### 5. Test Suite Alignment
*   **Directive:** Maintain 100% test coverage.
*   **Behavior:**
    *   Update `src/db/tests/test_integration.py` to verify the new `User` insertions, the `sysadmin` seeding, and the foreign key relationships on `StepDefinition`.
    *   Update `src/api/tests/test_main.py` to assert that a GET request to `/admin/` returns an HTTP 200.

###### Logging
The "Logs" section will record Claude's work. Please use the following format:
###### (Short summary of the work)
###### (Short summary of the work)
...
###### Logs

###### User & Project Models, Provenance FKs, Sysadmin Seed, SQLAdmin Dashboard
*   **§1 Core Ownership Models:** Added `User` model (`id`, `username`, `email`, `is_active` + `TimestampMixin`) and `Project` model (`id`, `name`, `description`, `user_id` FK + `TimestampMixin`) to `src/db/models.py`. Both models carry bidirectional `relationship()` properties back to `User`.
*   **§2 Provenance & Auditing:** Applied `TimestampMixin` to `StepDefinition`. Added `user_id` FK (`nullable=False`) to `StepDefinition`, `JobConfiguration`, and `Project`, with bidirectional relationships wired on `User` (`step_definitions`, `job_configurations`, `projects` back-populates). Updated `src/services/job_service.py::dispatch_dummy_job` to look up the sysadmin `User` from the session and pass `user_id` to the new `JobConfiguration` — necessary because the NOT NULL constraint would otherwise immediately break all dispatch calls in Stage 0. Migration `0005` hand-authored (`docker compose exec` blocked in sandbox): creates `users` and `projects` tables, adds `created_at`/`updated_at` + `user_id` (with named FK constraints) to `step_definitions`, adds `user_id` to `job_configurations`; `downgrade` reverses all six operations.
*   **§3 Auto-Seeding Sysadmin:** Updated `src/db/seed.py::seed_step_definitions` to first upsert a `User(username="sysadmin", email="admin@diffpype.local", is_active=True)` using `one_or_none` (idempotent). The sysadmin's `id` is then passed as `user_id` to the `StepDefinition` row on first creation.
*   **§4 SQLAdmin Integration:** Added `sqladmin==0.18.0` and `itsdangerous==2.2.0` to `pyproject.toml` (`uv lock` run; `uv sync --group test` installs locally). Created `src/api/admin.py` with five `ModelView` subclasses (`UserAdmin`, `ProjectAdmin`, `StepDefinitionAdmin`, `DummyImageAdmin`, `JobConfigurationAdmin`). Mounted via `Admin(app, engine)` in `src/api/main.py`; dashboard available at `/admin`. Added `src.api.admin` automodule to `docs/index.rst`.
*   **§5 Tests:** Added `user` fixture to `src/db/tests/conftest.py` (creates sysadmin in the transactional test session). Updated 4 existing integration tests (`test_step_definition_queue_roundtrip`, `test_job_configuration_roundtrip`, `test_dummy_image_job_configuration_relationship`, `test_job_configuration_timestamps_populated`) to accept `user` fixture and pass `user_id`. Added 3 new integration tests: `test_user_roundtrip` (full field round-trip), `test_step_definition_user_relationship` (back-populate via FK), `test_sysadmin_seeding_links_step_definition_to_user` (patches `seed.SessionLocal` to use the test engine, calls `seed_step_definitions()` and verifies committed state). Added `test_dispatch_dummy_job_assigns_sysadmin_as_owner` to `test_job_service.py`. Added `test_admin_index_returns_200` to `test_main.py`.
*   **Verification:** `DATABASE_URL=... REDIS_URL=... uv run pytest --ignore=src/db/tests -q` → **64 passed**. Integration tests (`src/db/tests`) run in Docker where the live DB is reachable.
*   **Action Required (human):**
    *   `docker compose build api worker_light worker_heavy`
    *   `docker compose up -d api`
    *   `docker compose exec api alembic upgrade head` → should report `0005 (head)`
    *   `docker compose exec api diffpype-manage reset-db` — re-seeds with sysadmin user
    *   `docker compose restart worker_light worker_heavy`
    *   Run full suite: `docker compose exec api uv run pytest --cov=src --cov-fail-under=90`
    *   Visit `http://localhost:8000/admin/` to verify the SQLAdmin dashboard loads.
*   **Operational fixes (same branch):** Added `name: diffpype` to the top level of `docker-compose.yml` to pin the Compose project name — prevents the "network not created for project" warning when running `docker compose run` from different shells. Added `filterwarnings = ["ignore:Please use 'import python_multipart':PendingDeprecationWarning"]` to `[tool.pytest.ini_options]` in `pyproject.toml` to suppress a third-party deprecation noise from the transitive `multipart` package pulled in by `sqladmin`.
*   **Git Workflow:** All changes on `feature/user_auth_and_admin`; to be merged via Pull Request against `main`.