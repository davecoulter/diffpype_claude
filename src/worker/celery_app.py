from celery import Celery
from celery.schedules import crontab

from src.core.config import settings
from src.core.logger import configure_logging
from src.core.tracing import setup_tracing
from src.db.enums import CeleryQueue
from src.db.session import engine
from src.worker.base_task import HARD_LIMIT_BUFFER_SECONDS

# Every task's enforced hard time_limit (soft + HARD_LIMIT_BUFFER_SECONDS) that
# broker-level redelivery must never precede — otherwise a still-healthy,
# legitimately-running task could be falsely treated as abandoned and handed to
# a second worker concurrently. 60s extra margin for SIGTERM/SIGKILL cleanup and
# broker round-trip time on top of the largest real ceiling (currently ingest).
_ALL_TASK_SOFT_TIME_LIMITS = (
    settings.staging_sync_soft_time_limit_seconds,
    settings.ingest_batch_soft_time_limit_seconds,
    settings.mosaic_drizzle_soft_time_limit_seconds,
    settings.cli_tool_soft_time_limit_seconds,
    settings.db_backup_soft_time_limit_seconds,
    settings.dlq_dump_soft_time_limit_seconds,
    settings.reconcile_stuck_jobs_soft_time_limit_seconds,
)
_VISIBILITY_TIMEOUT_SAFETY_MARGIN_SECONDS = 60
VISIBILITY_TIMEOUT_SECONDS = (
    max(_ALL_TASK_SOFT_TIME_LIMITS)
    + HARD_LIMIT_BUFFER_SECONDS
    + _VISIBILITY_TIMEOUT_SAFETY_MARGIN_SECONDS
)

# Configure JSON logging for the worker process (and any CLI path that imports
# the service/task layer) so all components stream structured logs to stdout.
configure_logging()

# Instrument Celery and the SQLAlchemy engine so worker task spans are exported and
# the trace context dispatched by the API propagates across the process boundary.
setup_tracing(engine=engine)

celery_app = Celery(
    "diffpype",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["src.worker.tasks"],
)

celery_app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    # How long an unacked message stays invisible before Redis considers the
    # worker holding it dead and redelivers it. Tied to the largest real,
    # enforced task ceiling (see VISIBILITY_TIMEOUT_SECONDS above) rather than
    # left at kombu's 3600s default, which had no relationship to any task's
    # actual runtime before every task declared an explicit time limit (doc 30).
    broker_transport_options={"visibility_timeout": VISIBILITY_TIMEOUT_SECONDS},
    # sqlalchemy-celery-beat's DatabaseScheduler reads/writes schedules here; it
    # defaults to the `celery_schema` Postgres schema (created by migration 0014).
    beat_dburi=settings.database_url,
    task_routes={
        "src.worker.tasks.dlq_dump": {"queue": "dead_letter"},
        "src.worker.tasks.run_ingest_batch": {"queue": CeleryQueue.HEAVY_MEMORY},
        "src.worker.tasks.run_mosaic_drizzle": {"queue": CeleryQueue.HEAVY_MEMORY},
        # Beat-triggered and dispatched I/O tasks land on the light queue; without
        # an explicit route they would go to the default queue no worker consumes.
        "src.worker.tasks.run_staging_sync": {"queue": CeleryQueue.LIGHT},
        "src.worker.tasks.sync_staging_cron": {"queue": CeleryQueue.LIGHT},
        "src.worker.tasks.reconcile_stuck_jobs_cron": {"queue": CeleryQueue.LIGHT},
    },
)


def _configure_beat_schedule(app: Celery, cfg) -> None:
    """Conditionally register the Celery Beat schedule based on settings."""
    if cfg.enable_db_backup_cron:
        app.conf.beat_schedule = {
            "nightly-db-backup": {
                "task": "src.worker.tasks.db_backup_cron",
                "schedule": crontab(minute=0, hour=0),
            }
        }


_configure_beat_schedule(celery_app, settings)
