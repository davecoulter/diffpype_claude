import bcrypt
from sqlalchemy.orm import Session

from src.core.config import settings
from src.db.models import Band, Instrument, User
from src.db.session import SessionLocal

# Baseline JWST reference data so a fresh sandbox is immediately usable. Central
# wavelengths are the filter pivot wavelengths in microns. The complete standard
# NIRCam (wide/medium/narrow) + MIRI imaging filter sets — not a curated subset —
# since a partial list means every not-yet-seen real filter is a fresh ingest
# failure (see the F115W gap found live during doc-28 genTests).
_SEED_INSTRUMENTS = ["NIRCam", "MIRI"]
_SEED_BANDS = [
    # NIRCam wide filters (short + long wavelength channel)
    ("F070W", 0.704),
    ("F090W", 0.902),
    ("F115W", 1.154),
    ("F150W", 1.501),
    ("F150W2", 1.659),
    ("F200W", 1.990),
    ("F277W", 2.776),
    ("F356W", 3.563),
    ("F444W", 4.421),
    # NIRCam medium filters
    ("F140M", 1.404),
    ("F162M", 1.626),
    ("F182M", 1.845),
    ("F210M", 2.095),
    ("F250M", 2.503),
    ("F300M", 2.996),
    ("F335M", 3.365),
    ("F360M", 3.621),
    ("F410M", 4.092),
    ("F430M", 4.280),
    ("F460M", 4.624),
    ("F480M", 4.834),
    # NIRCam narrow filters
    ("F164N", 1.644),
    ("F187N", 1.874),
    ("F212N", 2.121),
    ("F323N", 3.237),
    ("F405N", 4.055),
    ("F466N", 4.654),
    ("F470N", 4.707),
    # MIRI imaging filters
    ("F560W", 5.6),
    ("F770W", 7.7),
    ("F1000W", 10.0),
    ("F1130W", 11.3),
    ("F1280W", 12.8),
    ("F1500W", 15.0),
    ("F1800W", 18.0),
    ("F2100W", 21.0),
    ("F2550W", 25.5),
]


def _seed_reference_data(db: Session) -> None:
    """Get-or-create the baseline Instrument and Band reference rows, idempotently."""
    for name in _SEED_INSTRUMENTS:
        if db.query(Instrument).filter_by(name=name).one_or_none() is None:
            db.add(Instrument(name=name))
    for name, central_lambda in _SEED_BANDS:
        if db.query(Band).filter_by(name=name).one_or_none() is None:
            db.add(Band(name=name, central_lambda=central_lambda))


def seed_step_definitions() -> None:
    """Upsert the sysadmin User and baseline Instrument/Band reference data."""
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

        _seed_reference_data(db)
        db.commit()
    finally:
        db.close()
