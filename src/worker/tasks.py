import time

from structlog.contextvars import bind_contextvars

from src.core.logger import get_logger
from src.db.enums import JobStatus
from src.db.models import DummyImage
from src.db.session import SessionLocal
from src.worker.base_task import DiffpypeTask
from src.worker.celery_app import celery_app


@celery_app.task(base=DiffpypeTask, name="src.worker.tasks.sleep_and_update_status")
def sleep_and_update_status(
    image_id: int, sleep_duration: int = 5, correlation_id: str | None = None
) -> None:
    bind_contextvars(correlation_id=correlation_id)
    log = get_logger()
    log.info("task_started", image_id=image_id, sleep_duration=sleep_duration)

    time.sleep(sleep_duration)

    db = SessionLocal()
    try:
        image = db.get(DummyImage, image_id)
        image.status = JobStatus.COMPLETE
        db.commit()
    finally:
        db.close()

    log.info("task_completed", image_id=image_id)
