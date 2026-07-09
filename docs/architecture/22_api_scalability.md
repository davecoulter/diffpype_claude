##### 22: API Scalability & Versioning
**Version:** 0.3

###### Preamble
This document is Chunk C of the hardening sequence. Its focus is protecting the API from heavy load and establishing a stable HTTP contract. It introduces database connection pooling, moves all endpoints under an `/api/v1` prefix, and sets up pagination standards for future endpoints.

###### 1. Database Connection Pooling
*   **Directive:** Protect the PostgreSQL database from connection exhaustion when Celery concurrency scales up.
*   **Behavior:**
    *   In `src/core/config.py`, add `db_pool_size` and `db_max_overflow` to the `Settings` class.
    *   In `src/db/session.py`, update the `create_engine` call to explicitly set `pool_size=settings.db_pool_size` and `max_overflow=settings.db_max_overflow`.
*   **Testing:** Add a unit test in `src/core/tests/test_config.py` verifying that the `Settings` class correctly parses `DB_POOL_SIZE` and `DB_MAX_OVERFLOW` from the environment as integers and applies the correct default values when the variables are not set.
*   **Breaking Changes:** None.
*   **Compliance:** None.

###### 2. API Versioning & Synchronous Threading Note
*   **Directive:** Establish a stable HTTP contract independent of semantic repository tags, and document the threading model.
*   **Behavior:**
    *   In `src/api/main.py`, update the `app.include_router()` calls to mount the existing routers under an `/api/v1` prefix (e.g., `prefix="/api/v1"`).
    *   Update `src/ui/src/api.ts` so the React frontend fetches from the new paths (e.g., by updating the `API_URL` base constant or the fetch strings to include `/api/v1`).
    *   Add a brief docstring to the FastAPI routers (e.g., in `src/api/routes/jobs.py`) acknowledging the architectural trade-off of using synchronous `def` routes. Note that they block Uvicorn's thread pool but are currently required by our synchronous `psycopg2` driver to prevent event-loop freezing.
*   **Testing:** 
    *   **Prerequisite:** Before writing any new code, all existing route tests in `src/api/tests/test_jobs.py`, `src/api/tests/test_meta.py`, and `src/api/tests/test_main.py` MUST be updated to reference the `/api/v1/jobs/...` and `/api/v1/meta/...` paths.
    *   Add a test in `src/api/tests/test_main.py` confirming that the old unversioned paths (e.g. `GET /jobs` and `GET /meta/statuses`) return HTTP 404 after the prefix change. This guards against a misconfigured router accidentally serving both the old and new paths simultaneously.
*   **Breaking Changes:** **Breaking HTTP Contract.** Any external HTTP client hitting the root `/jobs` or `/meta` endpoints will immediately receive a 404. 
*   **Compliance:** The `diffpype-manage` CLI delegates directly to the Service Layer, bypassing HTTP. Therefore, per the API/CLI parity rule, no CLI command updates are required for this HTTP routing change.

###### 3. Pagination Standard
*   **Directive:** Prevent unbounded list returns on future endpoints.
*   **Behavior:**
    *   In `src/api/schemas.py`, create a reusable `PaginationParams` Pydantic model containing `limit: int = Field(default=100, ge=1, le=1000)` and `offset: int = Field(default=0, ge=0)`.
    *   *(Note: Since our only current list endpoint, `/meta/statuses`, returns a tiny fixed enum array, we do not need to apply this dependency to existing routes yet. This simply establishes the schema standard for future domain queries).*
*   **Testing:** Add a test in `src/api/tests/test_schemas.py` verifying that `PaginationParams` correctly enforces the `ge` and `le` bounds — specifically that `limit=0`, `limit=1001`, and `offset=-1` each raise a `ValidationError`, while valid boundary values (`limit=1`, `limit=1000`, `offset=0`) do not.
*   **Breaking Changes:** None.
*   **Compliance:** None.

###### 4. Environment Variables
*   **Directive:** Ensure all new configurations are tracked and synchronized.
*   **Note:** `.env.example` and `.env` must remain identical in their set of keys.

| Name | Type | Default Value | Description |
| :--- | :--- | :--- | :--- |
| `DB_POOL_SIZE` | int | `20` | The number of database connections to keep open in the connection pool. |
| `DB_MAX_OVERFLOW` | int | `10` | The number of temporary connections allowed beyond the pool size during spikes. |

###### 5. Dependencies & Packages
*   **Directive:** No new packages are required.
*   **Packages:** None.
*   **Mocking:** None.

###### 6. CLAUDE.md Compliance
*   **Toctree Registration:** Add `22_api_scalability` to the toctree in `docs/architecture/index.md`. Sphinx treats unlisted architecture files as orphans and fails the CI `-W` build.

###### Logs

###### 2026-07-08 — Implementation (Claude Sonnet 4.6)
*   **§1 DB Connection Pooling:** Added `db_pool_size: int = 20` and `db_max_overflow: int = 10` to `Settings` in `src/core/config.py`. Updated `create_engine` in `src/db/session.py` to pass `pool_size` and `max_overflow` from settings. Added `DB_POOL_SIZE` and `DB_MAX_OVERFLOW` to both `.env` and `.env.example`. Created `src/core/tests/__init__.py` and `src/core/tests/test_config.py` with 5 tests covering env-var parsing, defaults, and non-integer rejection.
*   **§2 API Versioning:** Updated `app.include_router()` calls in `src/api/main.py` to add `prefix="/api/v1"`. Updated all existing route tests in `test_jobs.py`, `test_meta.py`, and `test_main.py` to use `/api/v1/...` paths (prerequisite done before production code). Added two regression tests in `test_main.py` confirming the old unversioned `/jobs/...` and `/meta/...` paths return 404. Added sync-route trade-off comment to `src/api/routes/jobs.py`. Updated all 3 fetch URLs in `src/ui/src/api.ts` to include `/api/v1`.
*   **§3 Pagination Standard:** Added `PaginationParams` Pydantic model with `limit` (ge=1, le=1000, default=100) and `offset` (ge=0, default=0) to `src/api/schemas.py`. Created `src/api/tests/test_schemas.py` with 5 tests covering defaults, valid boundaries, and all three invalid boundary cases.
*   **§6 Toctree:** Added `22_api_scalability` to `docs/architecture/index.md`.
*   **Verification:** 23 tests pass; Sphinx build zero warnings.

###### 2026-07-08 — Bug fixes found during genTests Application QA

*   **Bug: `getDummyJobStatus` fetch URL missing `/api/v1` prefix.** Discovered during QA Step 4 — Chrome Network tab showed `GET /jobs/dummy/{id}` (old path) returning 404. Root cause: the Edit `replace_all` on `${API_URL}/jobs/dummy` matched the exact string in `createDummyJob` (followed by a closing backtick) but not the substring within `` `${API_URL}/jobs/dummy/${imageId}` `` in `getDummyJobStatus`. Fix: introduced a shared `API_BASE = \`${API_URL}/api/v1\`` constant (version-neutral name so it doesn't need renaming on a version bump) and updated all three fetch calls to use it, preventing any future partial-update of the version prefix.

*   **Bug: Frontend fetching old unversioned URL after rebuild.** Discovered during QA Step 4 — Chrome Network tab showed `GET /jobs/dummy/{id}` returning 404. Root cause: browser was serving a stale cached version of `api.ts` from Vite's dev server. The code on disk was correct. Fix: hard-refresh (Cmd+Shift+R) cleared the cache and the correct `/api/v1/...` URL was used immediately.

*   **Bug: `refetchInterval` polls indefinitely on query error.** Discovered during QA Step 4 — when `getDummyJobStatus` threw due to the stale URL returning 404, `query.state.data` was `undefined`, so `query.state.data?.status ?? ""` evaluated to `""`, which is not in `TERMINAL`, causing polling to continue forever. Fix: added an early `if (query.state.error) return false` guard in `refetchInterval` in `src/ui/src/pages/DashboardPage.tsx` so polling halts on any query error.