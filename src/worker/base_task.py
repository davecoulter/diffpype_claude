"""Celery base task providing the framework Boundary Pattern.

``DiffpypeTask.on_failure`` is the outer backstop for any exception that bubbles
out of a task body. It logs the crash with structlog, clears the (possibly
invalid) transaction state with an explicit ``rollback``, and transitions the
domain entity to ``JobStatus.FAILED`` so downstream consumers (the polling UI)
observe a terminal state instead of an orphaned ``in_process`` record.
"""
import celery
from sqlalchemy import func
from sqlalchemy.exc import OperationalError as SAOperationalError

from src.core.config import settings
from src.core.logger import get_logger
from src.db.enums import JobStatus
from src.db.models import DummyImage
from src.db.session import SessionLocal


class DiffpypeTask(celery.Task):
    """Base task that guarantees failure logging and DB transaction safety."""

    # Include SAOperationalError so transient DB connection drops are retried,
    # not just raw socket-level IOError/ConnectionError.
    autoretry_for = (IOError, OSError, ConnectionError, TimeoutError, SAOperationalError)
    max_retries = settings.celery_task_max_retries
    default_retry_delay = settings.celery_task_retry_delay

    def on_failure(self, exc, task_id, args, kwargs, einfo) -> None:
        # The active OTel task span supplies the correlation_id to every log line
        # via the structlog processor, so no manual context binding is needed here.
        image_id = args[0] if args else None
        log = get_logger()
        log.error(
            "task_failed",
            task_id=task_id,
            image_id=image_id,
            error=str(exc),
            exc_info=einfo,
        )

        # DB update and DLQ dispatch are intentionally separated: if the DB is
        # down, the status write fails but the DLQ dispatch (Redis-only) must
        # still fire so the task is never silently lost.
        db = SessionLocal()
        try:
            db.rollback()
            image = db.get(DummyImage, image_id)
            if image is not None:
                image.status = JobStatus.FAILED
                image.job_finished_at = func.now()
                db.commit()
        except Exception:
            log.error("on_failure_db_update_failed", task_id=task_id, exc_info=True)
        finally:
            db.close()

        try:
            from src.worker.tasks import dlq_dump  # lazy import avoids circular dependency
            dlq_dump.apply_async(
                kwargs={
                    "failed_task_name": self.name or task_id,
                    "task_kwargs": kwargs,
                    "error_msg": str(exc),
                },
                queue="dead_letter",
            )
        except Exception:
            log.error("on_failure_dlq_dispatch_failed", task_id=task_id, exc_info=True)
