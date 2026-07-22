import bcrypt
from sqlalchemy.orm import Session

from src.core.config import settings
from src.db.enums import CeleryQueue
from src.db.models import Band, Instrument, StepDefinition, User
from src.db.session import SessionLocal

# Baseline JWST reference data so a fresh sandbox is immediately usable. Central
# wavelengths are the filter pivot wavelengths in microns.
_SEED_INSTRUMENTS = ["NIRCam", "MIRI"]
_SEED_BANDS = [("F150W", 1.501), ("F277W", 2.776)]


def _seed_reference_data(db: Session) -> None:
    """Get-or-create the baseline Instrument and Band reference rows, idempotently."""
    for name in _SEED_INSTRUMENTS:
        if db.query(Instrument).filter_by(name=name).one_or_none() is None:
            db.add(Instrument(name=name))
    for name, central_lambda in _SEED_BANDS:
        if db.query(Band).filter_by(name=name).one_or_none() is None:
            db.add(Band(name=name, central_lambda=central_lambda))


def seed_step_definitions() -> None:
    """Upsert a sysadmin User, the dummy StepDefinition, and baseline Instrument/Band reference data."""
    db = SessionLocal()
    try:
        hashed = bcrypt.hashpw(
            settings.admin_password.encode("utf-8"), bcrypt.gensalt()
        ).decode("utf-8")
        sysadmin = db.query(User).filter_by(username="sysadmin").one_or_none()
        if sysadmin is None:
            sysadmin = User(
                username="sysadmin",
                email="admin@diffpype.local",
                is_active=True,
                hashed_password=hashed,
            )
            db.add(sysadmin)
            db.flush()
        else:
            sysadmin.hashed_password = hashed
            db.flush()

        exists = db.query(StepDefinition).filter_by(name="dummy_sleep").one_or_none()
        if exists is None:
            db.add(
                StepDefinition(
                    name="dummy_sleep",
                    task_name="src.worker.tasks.sleep_and_update_status",
                    queue=CeleryQueue.LIGHT,
                    user_id=sysadmin.id,
                )
            )

        _seed_reference_data(db)
        db.commit()
    finally:
        db.close()
