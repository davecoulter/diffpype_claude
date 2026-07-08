##### 20: Security & Access Control
**Version:** 0.4

###### Preamble
This document is Chunk A of the hardening sequence. Its singular focus is closing the critical security vulnerabilities currently present in the system: the completely unauthenticated SQLAdmin and Flower boundaries, and the overly permissive CORS policy. This ensures no unauthorized CRUD operations can occur on the database.

###### 1. User Passwords & Database Migration
*   **Directive:** The `User` model must support password hashing to enable authentication.
*   **Behavior:**
    *   In `src/db/models.py`, add a `hashed_password` column (String, `nullable=False`) to the `User` model.
    *   **Migration Strategy:** Use Alembic `--autogenerate` to create the migration script. Because the column is `nullable=False` and a `sysadmin` row already exists, the migration script must be hand-edited to first create the column as nullable, then backfill the existing `sysadmin` row with a temporary placeholder hash, and finally alter the column to `nullable=False`. The developer must review the output before applying it.
    *   Update `src/db/seed.py` so that when the `sysadmin` user is created, it assigns a secure hash derived from the `ADMIN_PASSWORD` environment variable.
*   **Testing:** Add a test verifying the `hashed_password` field round-trips to the database correctly.
*   **Breaking Changes:** None (database schema addition only).
*   **Compliance:** Alembic must be used. Wait for the developer to run `alembic upgrade head`.

###### 2. SQLAdmin Authentication Backend
*   **Prerequisite:** §1's Alembic migration must be applied and `seed-db` re-run before this section can be implemented or tested.
*   **Directive:** Lock down the `/admin` dashboard.
*   **Behavior:**
    *   In `src/api/admin.py`, implement an `AuthenticationBackend` (from `sqladmin.authentication`) that uses session cookies and `passlib.context.CryptContext` to verify credentials against the `User` table.
    *   Mount the `Admin` app in `src/api/main.py` using this backend.
*   **Testing:** 
    *   Create tests to verify SQLAdmin login success (returns 302 redirect or 200 with session), login failure (bad password), and session expiry/unauthenticated access (redirects to login).
    *   **Integration Test Isolation:** The SQLAdmin `AuthenticationBackend` opens its own `SessionLocal()` internally. Integration tests that exercise the login endpoint must use a real test database and explicitly clean up any committed `User` rows at the end of the test — the transactional rollback fixture in `conftest.py` will not capture them. Follow the same cleanup pattern established in `test_sysadmin_seeding_links_step_definition_to_user`.
*   **Breaking Changes:** **Immediate Lock.** The `/admin` endpoint is locked immediately upon deployment of this code. Unauthenticated users will no longer see the CRUD dashboard.
*   **Compliance:** Add `src.api.admin` to `autodoc_mock_imports` in `docs/conf.py` if `passlib` causes import errors during the Sphinx build. 

###### 3. CORS & Flower Lockdown
*   **Directive:** Restrict CORS origins and secure the Flower dashboard.
*   **Behavior:**
    *   **CORS:** In `src/api/main.py`, update `CORSMiddleware` to read `allow_origins` from the `CORS_ORIGINS` environment variable instead of the hardcoded `["*"]`.
    *   **Flower:** Update `docker-compose.yml` to pass basic authentication credentials to the Flower container via the `FLOWER_BASIC_AUTH` environment variable.
*   **Testing:** Add a test verifying that cross-origin HTTP requests outside of `CORS_ORIGINS` are rejected by FastAPI.
*   **Breaking Changes:** Any frontend client not running on `localhost:5173` (or whatever is defined in the env) will immediately lose API access.
*   **Compliance:** None.

###### 4. Environment Variables
*   **Directive:** Ensure all new configurations are tracked and synchronized. 
*   **Note:** `.env.example` and `.env` must remain identical in their set of keys.

| Name | Type | Default Value | Description |
| :--- | :--- | :--- | :--- |
| `ADMIN_USER` | str | `"sysadmin"` | The username for the default system administrator. |
| `ADMIN_PASSWORD` | str | `"changeme"` | The password for the default system administrator. |
| `FLOWER_BASIC_AUTH` | str | `"admin:changeme"` | The basic auth string (user:password) for the Flower monitoring dashboard. |
| `CORS_ORIGINS` | str | `"http://localhost:5173"` | A comma-separated string (e.g. `"http://localhost:5173,http://localhost:3000"`) of allowed CORS origins that the application will split on commas at startup. |

**⚠️ Credential security:** In `.env.example`, `ADMIN_PASSWORD` and `FLOWER_BASIC_AUTH` use placeholder values only — set strong unique values in your local `.env`. Register `ADMIN_PASSWORD` as a GitHub Actions secret: CI seeds the sysadmin user with a hashed password and runs auth integration tests against the real test database, so this value must be available to the workflow. Register `FLOWER_BASIC_AUTH` as a GitHub Actions secret as well, as production hygiene — it is not exercised in CI but must be secured in any non-local deployment.

###### 5. Dependencies & Packages
*   **Directive:** Add required packages for authentication.
*   **Packages:** Add `passlib==1.7.4` and `bcrypt==4.2.0` (required by passlib for bcrypt hashing) to `pyproject.toml`. 
*   **Mocking:** Note that `passlib` or `bcrypt` may need to be added to `autodoc_mock_imports` in `docs/conf.py`.

###### 6. CLAUDE.md Compliance
*   **Toctree Registration:** Add `20_security_and_access_control` to the toctree in `docs/architecture/index.md`. Sphinx treats unlisted architecture files as orphans and fails the CI `-W` build.

###### Logs
###### 2026-07-08 — Full implementation of §1–§3
Implemented all three sections. §1: added `hashed_password` (String, nullable=False) to the `User` model; hand-edited Alembic migration `0006` to add the column as nullable, backfill the existing sysadmin row, then alter to nullable=False. §2: implemented `DiffpypeAuthBackend` in `src/api/admin.py` using direct `bcrypt` calls (see decision below); mounted the `Admin` with the auth backend in `src/api/main.py`. §3: updated `CORSMiddleware` to read `allow_origins` from `settings.cors_origins` split on commas; added `FLOWER_BASIC_AUTH` to the Flower service in `docker-compose.yml`.

###### 2026-07-08 — Dropped passlib in favour of direct bcrypt
`passlib==1.7.4` is unmaintained and incompatible with `bcrypt>=4.0` (the library removed `__about__.__version__`, producing a noisy `(trapped) error reading bcrypt version` warning on every migration and seed run). Removed `passlib` from `pyproject.toml`, `docs/sphinx_requirements.txt`, and `docs/conf.py autodoc_mock_imports`. All hash/verify calls in `admin.py`, `seed.py`, the migration, and their tests now use `bcrypt.hashpw` / `bcrypt.checkpw` directly.

###### 2026-07-08 — Auth login bug fix and admin observability
Fixed two bugs discovered during manual testing: (1) `bcrypt.checkpw()` raises `ValueError` when the stored `hashed_password` is not a valid bcrypt hash (e.g. plain text entered via the admin form). The `login()` method now catches `ValueError` and logs a structured warning rather than propagating a 500. A broad `Exception` catch also logs unexpected errors explicitly — necessary because sqladmin is mounted as a sub-application and exceptions inside it never reach FastAPI's `@app.exception_handler`, making them otherwise invisible in logs. (2) Added `on_model_change` to `UserAdmin` to hash plain-text password input before it is persisted. The admin form now accepts a human-readable password and stores the bcrypt hash transparently.

###### 2026-07-08 — Admin form UX cleanup
Added `form_excluded_columns` to all five `ModelView` classes. For every model: excluded `created_at` and `updated_at` (server-managed via `TimestampMixin`, should never be user-editable). For `UserAdmin`: also excluded `projects`, `step_definitions`, `job_configurations` (one-to-many back-references that clutter the create/edit form). For `JobConfigurationAdmin`: excluded `dummy_images` (same reason). For `DummyImageAdmin`: excluded `job_started_at`, `job_finished_at`, and `latest_job_id` (all worker-stamped system fields). Many-to-one relationships (e.g. `user` on Project, `job_configuration` on DummyImage) are retained as they render as useful dropdown selectors.

###### 2026-07-08 — Implementation notes not explicit in the doc
- `ADMIN_SECRET_KEY` env var added to `Settings`, `.env.example`, `.env`, and `docker-compose.yml` (api service). Required by `AuthenticationBackend(secret_key=...)` for session-cookie signing — the doc mandated session auth but did not name this var. Default `"diffpype-dev-secret-key-change-in-production"` is safe for local dev only.
- API/CLI parity: N/A — no new FastAPI routes introduced; the admin dashboard is framework-provided by sqladmin.
- Sphinx automodule: N/A — no new business logic modules; `src.api.admin` remains in `autodoc_mock_imports` as a framework-glue module.
- `uv sync` (without `--all-groups`) strips test dependencies. Always use `uv sync --all-groups` in this project.