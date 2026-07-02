from src.db.enums import CeleryQueue
from src.db.models import StepDefinition
from src.db.session import SessionLocal


def seed_step_definitions() -> None:
    """Insert the dummy StepDefinition row if it doesn't already exist."""
    db = SessionLocal()
    try:
        exists = (
            db.query(StepDefinition)
            .filter_by(name="dummy_sleep")
            .one_or_none()
        )
        if exists is None:
            db.add(
                StepDefinition(
                    name="dummy_sleep",
                    task_name="src.worker.tasks.sleep_and_update_status",
                    queue=CeleryQueue.LIGHT,
                )
            )
            db.commit()
    finally:
        db.close()
