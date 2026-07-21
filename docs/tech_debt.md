# Diffpype Technical Debt & Deferred Fixes

### Preamble
This document tracks small workarounds, dependency pins, and known limitations that should be revisited later. It is distinct from `docs/prd.md` (deferred *product* features) and `CLAUDE.md` (agentic guardrails and workflow rules). Each entry should be actionable: what the item is, and the specific condition under which it can be resolved and removed.

### Open Items

#### Remove `setuptools<81` pin
*   **What:** `pyproject.toml` pins `setuptools<81` because `opentelemetry-instrumentation==0.48b0` imports `pkg_resources`, which setuptools removed starting in v81. Without the pin, all OTel instrumentors fail to import (`ModuleNotFoundError: No module named 'pkg_resources'`).
*   **Resolution condition:** Once the `opentelemetry-instrumentation-*` packages are upgraded past `0.48b0` to a version that no longer imports `pkg_resources`, remove the `setuptools<81` pin and the corresponding `ignore:pkg_resources is deprecated as an API:UserWarning` entry in `[tool.pytest.ini_options] filterwarnings`.
*   **Source:** `docs/architecture/23_observability.md`, added 2026-07-09.

#### Adopt React Router `v7_startTransition` future flag
*   **What:** React Router emits a future-flag warning in the browser console during manual UI testing, recommending `v7_startTransition` be enabled ahead of the v7 migration.
*   **Resolution condition:** One-liner opt-in — add `future: { v7_startTransition: true }` to the router config in `src/ui/`. Nothing is currently broken; the UI is fully functional without it.
*   **Source:** Surfaced during doc 20 manual UI testing, 2026-07-08. Originally logged in `CLAUDE.md`'s Clarifications; moved here 2026-07-09.

#### Unify CLI-triggered traces with an explicit root span
*   **What:** `diffpype-manage` CLI commands (e.g. `run-dummy`) don't wrap their pre/post-dispatch DB writes in a root span the way `FastAPIInstrumentor` automatically wraps HTTP requests. The Celery dispatch onward correctly forms one coherent trace (confirmed live); DB writes before `.delay()` do not join it.
*   **Resolution condition:** Wrap `cmd_run_dummy` (or `dispatch_dummy_job`) in an explicit `tracer.start_as_current_span(...)` if/when CLI-side observability parity with the API becomes a priority. Uncertain value — the core propagation requirement (trace context flows automatically from CLI-triggered dispatch through to the worker) already works without this.
*   **Source:** Verified live during doc 23 QA, 2026-07-09. Originally logged in `prd.md`'s Deferred/Future Scope; moved here 2026-07-09.

#### Implement real `db_backup_cron` + host-accessible backup/restore path
*   **What:** `ENABLE_DB_BACKUP_CRON` (doc 21) wires a nightly Celery Beat schedule to `src.worker.tasks.db_backup_cron`, but that task is a stub — it only logs `"Nightly backup triggered"` and performs no actual backup. There is currently no backup or restore mechanism for the `db` service's data at all.
*   **Resolution condition:** Implement `db_backup_cron` to actually run `pg_dump` (or `pg_basebackup`) against `db`, plus a corresponding restore path (CLI command or documented procedure). Proposed approach (discussed 2026-07-20): a hybrid volume strategy — keep `diffpype_db_data` (the live Postgres data directory) as a Docker-managed named volume, since Postgres's fsync/WAL durability and POSIX locking guarantees are safest there (this matters most on Docker Desktop for Mac, where a bind mount crosses the VM boundary via VirtioFS/gRPC-FUSE — not a concern on the real Linux production target, but still the right default regardless), and add a *second*, separate bind-mounted directory used only as the backup task's output destination, so dumps land on a real host path without touching how the live data directory is stored.
*   **Source:** Raised 2026-07-20 while reviewing the `db` image change in `docker-compose.prod.yml`; ties back to the `ENABLE_DB_BACKUP_CRON` toggle introduced in doc 21 (2026-07-09).

#### Publish multi-arch (`linux/amd64` + `linux/arm64`) images
*   **What:** `ci.yml`'s `build-and-push` job runs on GitHub's `ubuntu-latest` runners and never sets a target `platforms:`, so `docker/build-push-action` only produces `linux/amd64` images for `api`, `worker`, and `db`. Pulling and running them on an Apple Silicon (`arm64`) machine — confirmed live via `docker compose -f docker-compose.prod.yml up -d` on 2026-07-20 — works, but only under emulation, with a `platform does not match` warning for every affected service.
*   **Resolution condition:** Add `docker/setup-qemu-action` and `docker/setup-buildx-action` to the `build-and-push` job, and set `platforms: linux/amd64,linux/arm64` on the existing `docker/build-push-action` step for all three images. Produces a single multi-arch manifest per tag, so `docker pull` transparently selects the right architecture on any host — removing the warning and the emulation overhead rather than just detecting it. Expected cost: longer CI build time for the emulated `arm64` leg.
*   **Source:** Surfaced 2026-07-20 while verifying the `db` image publish fix locally on an Apple Silicon Mac.

### Resolved Items

#### Publish a `db` image to ghcr.io
*   **What it was:** `docker-compose.prod.yml` kept a `build:` context for `db` instead of pulling a published image, because CI's `build-and-push` matrix only covered `api` and `worker`.
*   **Resolution:** Added a `db` entry to the matrix in `.github/workflows/ci.yml`, and switched `docker-compose.prod.yml` to `image: ghcr.io/davecoulter/diffpype_claude-db:${IMAGE_TAG:-main}`. Note the corrected name — the image is `diffpype_claude-db`, not `diffpype-db` as originally recorded here; `github.repository` resolves to `davecoulter/diffpype_claude`, a naming mismatch first caught in the `api`/`worker` images and fixed the same way here. Guarded by `src/core/tests/test_docker_compose_prod.py`.
*   **Source:** Identified during doc 24 implementation, 2026-07-09. Resolved 2026-07-20.

### Logs
#### 2026-07-20
*   **Action:** Resolved the "Publish a `db` image to ghcr.io" item — added `db` to `ci.yml`'s `build-and-push` matrix and switched `docker-compose.prod.yml` to pull `ghcr.io/davecoulter/diffpype_claude-db` (corrected from the originally-recorded `diffpype-db` name). Added a regression test in `src/core/tests/test_docker_compose_prod.py` covering all three images (`api`, `worker`, `db`) plus confirming `db` no longer builds locally.
*   **Action:** Added the `db_backup_cron`/backup-restore/hybrid-volume item above, surfaced while discussing production storage for the `db` service.
*   **Action:** Verified the `db` image publish fix end-to-end via `docker compose -f docker-compose.prod.yml pull && up -d` on an Apple Silicon Mac — all three services pulled and started successfully, confirming the ghcr.io naming fix works. Surfaced a `linux/amd64`-only platform warning in the process; logged as a new multi-arch tech-debt item above rather than fixed inline, since it's orthogonal to the naming fix.

#### 2026-07-09
*   **Action:** Created this document to track technical debt separately from product-scope deferrals (`prd.md`) and agentic guardrails (`CLAUDE.md`). Added the `setuptools<81` pin as the first tracked item.
*   **Action:** Ported two items previously scattered elsewhere: the React Router future-flag warning (moved from `CLAUDE.md`'s Clarifications) and the CLI root-span gap (moved from `prd.md`'s Deferred/Future Scope). Both are code-level gaps in already-shipped work, not unbuilt product features, so they fit this document's scope better than `prd.md`'s.
*   **Action:** Added the missing `db` ghcr.io image publishing gap, found while implementing doc 24's `docker-compose.prod.yml`.
