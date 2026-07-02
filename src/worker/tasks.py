import time

from src.db.enums import JobStatus
from src.db.models import DummyImage
from src.db.session import SessionLocal
from src.worker.celery_app import celery_app


@celery_app.task(name="src.worker.tasks.sleep_and_update_status")
def sleep_and_update_status(image_id: int) -> None:
    time.sleep(5)
    db = SessionLocal()
    try:
        image = db.get(DummyImage, image_id)
        image.status = JobStatus.COMPLETE
        db.commit()
    finally:
        db.close()
