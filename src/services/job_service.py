from sqlalchemy.orm import Session
from structlog.contextvars import get_contextvars

from src.core.logger import get_logger
from src.db.enums import JobStatus
from src.db.models import DummyImage
from src.worker.tasks import sleep_and_update_status


def dispatch_dummy_job(db: Session, config: dict) -> tuple[str, int]:
    """Persist a DummyImage with its config, dispatch the sleep task, return (job_id, image_id).

    The active ``correlation_id`` (bound by the FastAPI middleware, if any) is
    forwarded into the Celery task so the worker can re-bind the same ID and the
    request can be traced across the process boundary.
    """
    log = get_logger()
    correlation_id = get_contextvars().get("correlation_id")

    image = DummyImage(status=JobStatus.IN_PROCESS, job_kwargs=config)
    db.add(image)
    db.commit()
    db.refresh(image)

    async_result = sleep_and_update_status.delay(
        image.id, config["sleep_duration"], correlation_id=correlation_id
    )

    image.latest_job_id = async_result.id
    db.commit()

    log.info(
        "dummy_job_dispatched",
        image_id=image.id,
        job_id=async_result.id,
    )
    return async_result.id, image.id
