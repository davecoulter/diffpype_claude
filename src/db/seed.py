from src.db.enums import CeleryQueue
from src.db.models import StepDefinition, User
from src.db.session import SessionLocal


def seed_step_definitions() -> None:
    """Upsert a sysadmin User and the dummy StepDefinition row owned by that user."""
    db = SessionLocal()
    try:
        sysadmin = db.query(User).filter_by(username="sysadmin").one_or_none()
        if sysadmin is None:
            sysadmin = User(
                username="sysadmin",
                email="admin@diffpype.local",
                is_active=True,
            )
            db.add(sysadmin)
            db.flush()

        exists = (
            db.query(StepDefinition).filter_by(name="dummy_sleep").one_or_none()
        )
        if exists is None:
            db.add(
                StepDefinition(
                    name="dummy_sleep",
                    task_name="src.worker.tasks.sleep_and_update_status",
                    queue=CeleryQueue.LIGHT,
                    user_id=sysadmin.id,
                )
            )
        db.commit()
    finally:
        db.close()
