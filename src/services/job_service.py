from sqlalchemy.orm import Session

from src.db.enums import JobStatus
from src.db.models import DummyImage
from src.worker.tasks import sleep_and_update_status


def dispatch_dummy_job(db: Session) -> tuple[str, int]:
    """Create a DummyImage row, dispatch the sleep task, and return (job_id, image_id)."""
    image = DummyImage(status=JobStatus.IN_PROCESS)
    db.add(image)
    db.commit()
    db.refresh(image)

    async_result = sleep_and_update_status.delay(image.id)

    image.latest_job_id = async_result.id
    db.commit()

    return async_result.id, image.id
