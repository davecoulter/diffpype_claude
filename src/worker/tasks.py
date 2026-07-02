import time

from src.db.enums import JobStatus
from src.db.models import DummyImage
from src.db.session import SessionLocal
from src.worker.celery_app import celery_app


@celery_app.task(name="src.worker.tasks.sleep_and_update_status")
def sleep_and_update_status(image_id: int, sleep_duration: int = 5) -> None:
    db = SessionLocal()
    try:
        time.sleep(sleep_duration)
        image = db.get(DummyImage, image_id)
        image.status = JobStatus.COMPLETE
        db.commit()
    except Exception:
        # Best-effort: write FAILED to Postgres so the UI stops polling
        # and transitions to the red error indicator instead of spinning forever.
        try:
            db.rollback()
            image = db.get(DummyImage, image_id)
            if image is not None:
                image.status = JobStatus.FAILED
                db.commit()
        except Exception:
            pass  # If the failure write itself fails, Flower still has the trace.
        raise   # Re-raise so Celery records FAILED in Redis.
    finally:
        db.close()
