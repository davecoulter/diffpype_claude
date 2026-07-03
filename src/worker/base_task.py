"""Celery base task providing the framework Boundary Pattern.

``DiffpypeTask.on_failure`` is the outer backstop for any exception that bubbles
out of a task body. It logs the crash with structlog, clears the (possibly
invalid) transaction state with an explicit ``rollback``, and transitions the
domain entity to ``JobStatus.FAILED`` so downstream consumers (the polling UI)
observe a terminal state instead of an orphaned ``in_process`` record.
"""
import celery
from structlog.contextvars import bind_contextvars

from src.core.logger import get_logger
from src.db.enums import JobStatus
from src.db.models import DummyImage
from src.db.session import SessionLocal


class DiffpypeTask(celery.Task):
    """Base task that guarantees failure logging and DB transaction safety."""

    def on_failure(self, exc, task_id, args, kwargs, einfo) -> None:
        image_id = args[0] if args else None
        correlation_id = kwargs.get("correlation_id")
        if correlation_id:
            bind_contextvars(correlation_id=correlation_id)

        log = get_logger()
        log.error(
            "task_failed",
            task_id=task_id,
            image_id=image_id,
            error=str(exc),
            exc_info=einfo,
        )

        db = SessionLocal()
        try:
            # Clear any invalid transaction state left by the failed task body
            # before writing the terminal FAILED status.
            db.rollback()
            image = db.get(DummyImage, image_id)
            if image is not None:
                image.status = JobStatus.FAILED
                db.commit()
        finally:
            db.close()
