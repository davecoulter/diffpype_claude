##### 21: Worker Reliability (Retries, DLQ, & Beat)
**Version:** 0.2

###### Preamble
This document is Chunk B of the hardening sequence. Its singular focus is ensuring the Celery worker infrastructure is resilient to transient failures and capable of safely parking permanently failed jobs. It introduces automated task retries, a manual Dead Letter Queue (DLQ) pattern for Redis, and Celery Beat for scheduled cron jobs.

###### 1. Automated Task Retries
*   **Directive:** Ensure transient errors (e.g., temporary DB connection drops or S3 timeouts) do not instantly fail a job.
*   **Behavior:**
    *   Update `DiffpypeTask` in `src/worker/base_task.py`.
    *   Set the class-level attributes to retry only on transient I/O and network errors: `autoretry_for = (IOError, OSError, ConnectionError, TimeoutError)`. This intentionally excludes programming errors (e.g. `ValueError`, `TypeError`) so that corrupt inputs fail immediately to `on_failure` rather than burning retries.
    *   Bind `max_retries` to the `CELERY_TASK_MAX_RETRIES` environment variable.
    *   Bind `default_retry_delay` to the `CELERY_TASK_RETRY_DELAY` environment variable.
*   **Testing:** Add a unit test in `src/worker/tests/test_base_task.py` verifying that a `ConnectionError` raised in a task body triggers a retry (via Celery's `Retry` exception) rather than immediately invoking `on_failure`. Add a second test verifying that a `ValueError` (a non-retryable exception) does NOT trigger a retry and instead immediately invokes `on_failure`.
*   **Breaking Changes:** None.

###### 2. Dead Letter Queue (DLQ)
*   **Directive:** Permanently failed tasks (after exhausting retries) must not disappear silently. Because Redis does not have native AMQP dead-letter exchanges, we must route them manually.
*   **Behavior:**
    *   In `src/worker/celery_app.py`, globally configure `task_acks_late = True` and `task_reject_on_worker_lost = True` to prevent silent task drops if a worker container crashes mid-execution.
    *   In `src/worker/tasks.py`, create a simple `dlq_dump(failed_task_name: str, task_kwargs: dict, error_msg: str)` task that simply logs the payload via `structlog`. Route this task exclusively to a new `dead_letter` queue in `task_routes`.
    *   Update `DiffpypeTask.on_failure` in `src/worker/base_task.py` to dispatch `dlq_dump.apply_async(queue="dead_letter")` with the failed task's payload just before it closes the database session.
    *   Add `dead_letter` to the queue list consumed by `worker_light` in `docker-compose.yml`. The `dlq_dump` task is log-only and lightweight; `worker_light` is the correct consumer. Without this change, dead-letter messages will accumulate in Redis unprocessed.
*   **Testing:** 
    *   Verify `dlq_dump` is called with the correct queue routing when `on_failure` is invoked.
    *   **Framework Session Isolation Flag:** `DiffpypeTask.on_failure` opens its own `SessionLocal()`. Any integration tests exercising this must manually clean up committed rows, as the standard `conftest.py` transactional rollback will not catch them.
*   **Breaking Changes:** Setting `task_acks_late = True` changes the worker's message delivery guarantee from at-most-once to at-least-once. If a worker container crashes mid-task, Redis re-queues the message and the task restarts from the beginning. All tasks in this system must be idempotent (safe to run more than once) for this setting to be safe.
*   **Compliance:** Adding `dead_letter` to `task_routes` changes the worker queue topology. Per CLAUDE.md Operational Gotchas, run `docker compose restart worker_light worker_heavy` after deploying this change to clear stale in-memory task routing.

###### 3. Celery Beat (Scheduled Tasks)
*   **Directive:** Establish the foundation for recurring cron jobs (like nightly database backups or stale file cleanup).
*   **Behavior:**
    *   In `src/worker/celery_app.py`, conditionally configure `celery_app.conf.beat_schedule` only if the `ENABLE_DB_BACKUP_CRON` environment variable is `True`.
    *   If `True`, register a dummy schedule (e.g., `crontab(minute=0, hour=0)`) pointing to a new `db_backup_cron` task in `src/worker/tasks.py`.
    *   The `db_backup_cron` task should simply log "Nightly backup triggered" via `structlog` for now (actual backup implementation is deferred to the DevOps chunk).
*   **Testing:** Add a test in `src/worker/tests/test_celery_app.py` verifying the beat schedule dictionary is populated when `ENABLE_DB_BACKUP_CRON` is `True`, and empty (or absent) when `False`.

###### 4. Environment Variables
*   **Directive:** Ensure all new configurations are tracked and synchronized.
*   **Note:** `.env.example` and `.env` must remain identical in their set of keys.

| Name | Type | Default Value | Description |
| :--- | :--- | :--- | :--- |
| `CELERY_TASK_MAX_RETRIES` | int | `3` | The maximum number of times a worker will retry a failed task. |
| `CELERY_TASK_RETRY_DELAY` | int | `60` | The delay in seconds between task retry attempts. |
| `ENABLE_DB_BACKUP_CRON` | bool | `False` | Toggle to enable/disable Celery Beat scheduled tasks. |

###### 5. Dependencies & Packages
*   **Directive:** No new packages are required (Celery Beat is built into `celery`).
*   **Packages:** None.
*   **Mocking:** None.

###### 6. CLAUDE.md Compliance
*   **Toctree Registration:** Add `21_worker_reliability` to the toctree in `docs/architecture/index.md`. Sphinx treats unlisted architecture files as orphans and fails the CI `-W` build.

###### Logs
###### 2026-07-08 — Full implementation of §1–§3
§1: Added `autoretry_for = (IOError, OSError, ConnectionError, TimeoutError)`, `max_retries`, and `default_retry_delay` as class-level attributes on `DiffpypeTask`, bound to the three new `Settings` fields. §2: Added `task_acks_late = True` and `task_reject_on_worker_lost = True` to `celery_app.conf`; added `dlq_dump` task in `tasks.py` (plain task, no `base=DiffpypeTask` to avoid infinite recursion); updated `DiffpypeTask.on_failure` to dispatch `dlq_dump.apply_async(queue="dead_letter")` via a lazy import before closing the DB session; added `dead_letter` to `worker_light`'s `CELERY_QUEUES` in `docker-compose.yml`. §3: Extracted `_configure_beat_schedule(app, cfg)` as a named function (enables unit testing without module reload); conditionally populates `beat_schedule` with the `db_backup_cron` nightly task when `ENABLE_DB_BACKUP_CRON=true`. Three new env vars added to `Settings`, `.env.example`, `.env`, and both worker services in `docker-compose.yml`.

###### 2026-07-09 — Bug fixes: SAOperationalError not retried; on_failure crashes when DB is down
Two bugs discovered during manual QA (stopping the DB to trigger a real connection failure):
(1) `sqlalchemy.exc.OperationalError` — what SQLAlchemy raises for DB connection drops — was not in `autoretry_for`. Only raw Python exceptions (`IOError`, `OSError`, `ConnectionError`, `TimeoutError`) were listed. Result: DB connection failures bypassed retries entirely and went straight to `on_failure`. Fix: added `SAOperationalError` to `autoretry_for`.
(2) `on_failure` opens its own `SessionLocal()` to write the FAILED status. When the DB is down, this also raises `OperationalError`, crashing `on_failure` before the DLQ dispatch could run — the task silently disappeared. Fix: split `on_failure` into two independent try/except blocks — one for the DB status update (fails gracefully when DB is down, logs `on_failure_db_update_failed`), one for the DLQ dispatch (Redis-only, always runs). Added regression test `test_on_failure_dispatches_dlq_even_when_db_is_down`.

###### 2026-07-08 — Coverage config fix
Added `[tool.coverage.run] omit = ["src/*/tests/*"]` to `pyproject.toml`. Pre-existing gap: the local `--ignore=src/db/tests` run excluded integration tests from collection but not from coverage measurement, causing `src/db/tests/conftest.py` and `src/db/tests/test_integration.py` (157 lines at 0%) to drag total coverage below the 90% threshold. Omitting test subdirectories from coverage measurement brings the local run to 95.94%. CI runs with a real DB so integration tests execute and this was not a CI failure.
