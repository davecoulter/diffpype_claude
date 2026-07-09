"""Business logic for dispatching dummy jobs, shared by the API and CLI boundaries."""
from sqlalchemy.orm import Session

from src.core.logger import get_logger
from src.db.enums import JobStatus
from src.db.models import DummyImage, JobConfiguration, User
from src.worker.tasks import sleep_and_update_status


def get_dummy_job(db: Session, image_id: int) -> DummyImage | None:
    """Return the DummyImage with the given primary key, or None if not found."""
    return db.get(DummyImage, image_id)


def dispatch_dummy_job(db: Session, config: dict) -> tuple[str, int]:
    """Persist a JobConfiguration + DummyImage, dispatch the sleep task, return (job_id, image_id).

    OpenTelemetry's Celery instrumentation propagates the active trace context into
    the dispatched task automatically, so no correlation ID is threaded by hand.
    """
    log = get_logger()

    sysadmin = db.query(User).filter_by(username="sysadmin").one()
    job_configuration = JobConfiguration(
        job_kwargs=config,
        execution_command=f"diffpype-manage run-dummy --sleep {config['sleep_duration']}",
        user_id=sysadmin.id,
    )
    image = DummyImage(status=JobStatus.IN_PROCESS, job_configuration=job_configuration)
    db.add(image)
    db.commit()
    db.refresh(image)

    async_result = sleep_and_update_status.delay(image.id, config["sleep_duration"])

    image.latest_job_id = async_result.id
    db.commit()

    log.info(
        "dummy_job_dispatched",
        image_id=image.id,
        job_id=async_result.id,
        job_configuration_id=job_configuration.id,
    )
    return async_result.id, image.id
