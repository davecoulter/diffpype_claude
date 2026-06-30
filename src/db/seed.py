from src.db.models import Base, StepDefinition
from src.db.session import SessionLocal, engine


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
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
                    queue="light",
                )
            )
            db.commit()
    finally:
        db.close()
