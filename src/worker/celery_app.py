from celery import Celery
from celery.schedules import crontab

from src.core.config import settings
from src.core.logger import configure_logging
from src.db.enums import CeleryQueue

# Configure JSON logging for the worker process (and any CLI path that imports
# the service/task layer) so all components stream structured logs to stdout.
configure_logging()

celery_app = Celery(
    "diffpype",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["src.worker.tasks"],
)

celery_app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_routes={
        "src.worker.tasks.sleep_and_update_status": {"queue": CeleryQueue.LIGHT},
        "src.worker.tasks.dlq_dump": {"queue": "dead_letter"},
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
