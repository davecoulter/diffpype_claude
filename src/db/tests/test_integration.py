"""Integration tests that run against a live PostgreSQL instance.

These tests validate that:
  - Alembic migrations materialize the correct Postgres enum types and tables.
  - SQLAlchemy ORM enum mappings round-trip correctly through the database.
  - Status transitions write and read back the expected Python enum instances.
  - The JobConfiguration table and its relationship to DummyImage round-trip correctly.
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from src.db.enums import CeleryQueue, JobStatus
from src.db.models import (
    Band,
    DummyImage,
    Epoch,
    Instrument,
    JobConfiguration,
    Level2Calibration,
    Level2Image,
    Level3Mosaic,
    Project,
    StepDefinition,
    Tile,
    User,
    tile_level2_calibration_association,
)


def test_job_status_enum_type_exists_in_db(db):
    rows = db.execute(
        text("SELECT unnest(enum_range(NULL::job_status))::text ORDER BY 1")
    ).fetchall()
    assert {r[0] for r in rows} == {"complete", "failed", "in_process", "pending"}


def test_celery_queue_enum_type_exists_in_db(db):
    rows = db.execute(
        text("SELECT unnest(enum_range(NULL::celery_queue))::text ORDER BY 1")
    ).fetchall()
    assert {r[0] for r in rows} == {"gpu", "heavy_memory", "light"}


def test_dummy_image_status_roundtrip(db):
    image = DummyImage(status=JobStatus.IN_PROCESS)
    db.add(image)
    db.flush()

    fetched = db.get(DummyImage, image.id)
    assert fetched.status == JobStatus.IN_PROCESS
    assert isinstance(fetched.status, JobStatus)

    fetched.status = JobStatus.COMPLETE
    db.flush()

    updated = db.get(DummyImage, image.id)
    assert updated.status == JobStatus.COMPLETE


def test_step_definition_queue_roundtrip(db, user):
    step = StepDefinition(
        name="integration_test_step",
        task_name="src.worker.tasks.sleep_and_update_status",
        queue=CeleryQueue.LIGHT,
        user_id=user.id,
    )
    db.add(step)
    db.flush()

    fetched = db.get(StepDefinition, step.id)
    assert fetched.queue == CeleryQueue.LIGHT
    assert isinstance(fetched.queue, CeleryQueue)


def test_all_job_status_transitions(db):
    """Every status value in the enum can be written to and read from the DB."""
    for status in JobStatus:
        image = DummyImage(status=status)
        db.add(image)
        db.flush()
        assert db.get(DummyImage, image.id).status == status


def test_job_configuration_roundtrip(db, user):
    config = JobConfiguration(
        job_kwargs={"sleep_duration": 7},
        execution_command="diffpype-manage run-dummy --sleep 7",
        user_id=user.id,
    )
    db.add(config)
    db.flush()

    fetched = db.get(JobConfiguration, config.id)
    assert fetched.job_kwargs == {"sleep_duration": 7}
    assert fetched.execution_command == "diffpype-manage run-dummy --sleep 7"


def test_dummy_image_job_configuration_relationship(db, user):
    config = JobConfiguration(
        job_kwargs={"sleep_duration": 3},
        execution_command="diffpype-manage run-dummy --sleep 3",
        user_id=user.id,
    )
    image = DummyImage(status=JobStatus.IN_PROCESS, job_configuration=config)
    db.add(image)
    db.flush()

    fetched = db.get(DummyImage, image.id)
    # Forward relationship: image -> its configuration.
    assert fetched.job_configuration_id == config.id
    assert fetched.job_configuration.job_kwargs == {"sleep_duration": 3}
    # Back-populated relationship: configuration -> its images.
    assert fetched in config.dummy_images


def test_dummy_image_job_configuration_nullable(db):
    image = DummyImage(status=JobStatus.PENDING)
    db.add(image)
    db.flush()

    fetched = db.get(DummyImage, image.id)
    assert fetched.job_configuration_id is None
    assert fetched.job_configuration is None


def test_dummy_image_timestamps_populated(db):
    """The TimestampMixin server defaults populate created_at/updated_at on insert."""
    image = DummyImage(status=JobStatus.PENDING)
    db.add(image)
    db.flush()
    db.refresh(image)

    assert image.created_at is not None
    assert image.updated_at is not None
    # job_started_at/job_finished_at remain null until the worker stamps them.
    assert image.job_started_at is None
    assert image.job_finished_at is None


def test_job_configuration_timestamps_populated(db, user):
    """The TimestampMixin server defaults populate created_at/updated_at on insert."""
    config = JobConfiguration(
        job_kwargs={"sleep_duration": 5},
        execution_command="diffpype-manage run-dummy --sleep 5",
        user_id=user.id,
    )
    db.add(config)
    db.flush()
    db.refresh(config)

    assert config.created_at is not None
    assert config.updated_at is not None


def test_user_roundtrip(db):
    """User model persists and round-trips all fields correctly."""
    u = User(
        username="testuser",
        email="test@example.com",
        is_active=True,
        hashed_password="dummy_hash_for_testing",
    )
    db.add(u)
    db.flush()
    db.refresh(u)

    fetched = db.get(User, u.id)
    assert fetched.username == "testuser"
    assert fetched.email == "test@example.com"
    assert fetched.is_active is True
    assert fetched.hashed_password == "dummy_hash_for_testing"
    assert fetched.created_at is not None
    assert fetched.updated_at is not None


def test_hashed_password_roundtrip(db):
    """hashed_password field persists to and reads back from the database correctly."""
    import bcrypt

    hashed = bcrypt.hashpw(b"testpassword", bcrypt.gensalt()).decode("utf-8")

    u = User(
        username="pwdtestuser",
        email="pwdtest@example.com",
        is_active=True,
        hashed_password=hashed,
    )
    db.add(u)
    db.flush()
    db.refresh(u)

    fetched = db.get(User, u.id)
    assert fetched.hashed_password == hashed
    assert bcrypt.checkpw(b"testpassword", fetched.hashed_password.encode("utf-8"))
    assert not bcrypt.checkpw(b"wrongpassword", fetched.hashed_password.encode("utf-8"))


def test_step_definition_user_relationship(db, user):
    """StepDefinition.user back-populates correctly when user_id is set."""
    step = StepDefinition(
        name="provenance_test_step",
        task_name="src.worker.tasks.sleep_and_update_status",
        queue=CeleryQueue.LIGHT,
        user_id=user.id,
    )
    db.add(step)
    db.flush()

    fetched = db.get(StepDefinition, step.id)
    assert fetched.user_id == user.id
    assert fetched.user.username == user.username


def test_sysadmin_seeding_links_step_definition_to_user(mocker, test_engine):
    """seed_step_definitions upserts a sysadmin User and assigns them to the StepDefinition."""
    from src.db.seed import seed_step_definitions

    TestSession = sessionmaker(bind=test_engine)
    mocker.patch("src.db.seed.SessionLocal", side_effect=TestSession)

    seed_step_definitions()

    db = TestSession()
    try:
        sysadmin = db.query(User).filter_by(username="sysadmin").one_or_none()
        assert sysadmin is not None
        assert sysadmin.email == "admin@diffpype.local"
        assert sysadmin.is_active is True
        assert (
            sysadmin.hashed_password is not None and len(sysadmin.hashed_password) > 0
        )
        step = db.query(StepDefinition).filter_by(name="dummy_sleep").one_or_none()
        assert step is not None
        assert step.user_id == sysadmin.id
    finally:
        db.close()

    # Committed outside the transactional fixture — must clean up explicitly so the
    # unique constraint on username doesn't bleed into subsequent tests. Delete
    # JobConfiguration rows referencing this user first: any code path that dispatches
    # a job as sysadmin (including manual CLI testing against this DB) can create one,
    # and it would otherwise block the User delete via fk_job_configurations_user_id.
    # seed_step_definitions also commits reference Instruments/Bands — remove them too.
    _cleanup_seeded_rows(TestSession)


def _cleanup_seeded_rows(TestSession):
    """Delete every row seed_step_definitions() commits outside the transactional fixture."""
    cleanup = TestSession()
    try:
        sysadmin_id = cleanup.query(User.id).filter_by(username="sysadmin").scalar()
        if sysadmin_id is not None:
            cleanup.query(JobConfiguration).filter_by(user_id=sysadmin_id).delete()
        cleanup.query(StepDefinition).filter_by(name="dummy_sleep").delete()
        cleanup.query(User).filter_by(username="sysadmin").delete()
        cleanup.query(Instrument).filter(
            Instrument.name.in_(["NIRCam", "MIRI"])
        ).delete(synchronize_session=False)
        cleanup.query(Band).filter(Band.name.in_(["F150W", "F277W"])).delete(
            synchronize_session=False
        )
        cleanup.commit()
    finally:
        cleanup.close()


# --- Domain model tests (doc 26) ---
#
# Helpers build a valid FK graph inside the transactional `db` fixture. All
# reference names carry a "-test" suffix so they never collide with the real
# NIRCam/MIRI/F150W/F277W rows that seed_step_definitions() commits (per the
# integration-test isolation rule in CLAUDE.md).


def _utc(year: int, month: int, day: int) -> datetime:
    return datetime(year, month, day, tzinfo=timezone.utc)


def _make_ref(db, instr_name="NIRCam-test", band_name="F150W-test"):
    instrument = Instrument(name=instr_name)
    band = Band(name=band_name, central_lambda=1.501)
    db.add_all([instrument, band])
    db.flush()
    return instrument, band


def _make_tile(db, project, name="Tile-test", ra=150.12, decl=2.31):
    tile = Tile(
        name=name,
        ra=ra,
        decl=decl,
        delta_ra=0.0417,
        delta_decl=0.0417,
        project_id=project.id,
    )
    db.add(tile)
    db.flush()
    return tile


def _make_epoch(db, project, tile, band):
    epoch = Epoch(
        start_date=_utc(2024, 1, 1),
        end_date=_utc(2024, 1, 5),
        start_mjd=60310.0,
        end_mjd=60314.0,
        project_id=project.id,
        tile_id=tile.id,
        band_id=band.id,
    )
    db.add(epoch)
    db.flush()
    return epoch


def _make_image(db, instrument, band, base_filename="jw001_cal.fits"):
    img = Level2Image(
        base_filename=base_filename,
        ra=150.12,
        decl=2.31,
        exp_time=1000.0,
        mjd_avg=60312.0,
        target_name="TESTTARGET",
        obs_start=_utc(2024, 1, 2),
        instrument_id=instrument.id,
        band_id=band.id,
    )
    db.add(img)
    db.flush()
    return img


def _make_calibration(db, image):
    cal = Level2Calibration(
        level2_image_id=image.id,
        current_file_ext=".fits",
        plate_scale=0.031,
    )
    db.add(cal)
    db.flush()
    return cal


def test_instrument_and_band_roundtrip(db):
    """Reference tables persist and read back all fields correctly."""
    instrument, band = _make_ref(db)
    fetched_instr = db.get(Instrument, instrument.id)
    fetched_band = db.get(Band, band.id)
    assert fetched_instr.name == "NIRCam-test"
    assert fetched_band.name == "F150W-test"
    assert fetched_band.central_lambda == 1.501
    assert fetched_instr.created_at is not None


def test_instrument_name_is_unique(db):
    """A duplicate Instrument name is rejected by the database."""
    db.add(Instrument(name="DupInstr-test"))
    db.flush()
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            db.add(Instrument(name="DupInstr-test"))
            db.flush()


def test_band_name_is_unique(db):
    """A duplicate Band name is rejected by the database."""
    db.add(Band(name="DupBand-test", central_lambda=1.0))
    db.flush()
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            db.add(Band(name="DupBand-test", central_lambda=2.0))
            db.flush()


def test_seed_reference_data_is_idempotent(mocker, test_engine):
    """Calling seed_step_definitions() twice must not raise or duplicate reference rows."""
    from src.db.seed import seed_step_definitions

    TestSession = sessionmaker(bind=test_engine)
    mocker.patch("src.db.seed.SessionLocal", side_effect=TestSession)

    seed_step_definitions()
    seed_step_definitions()  # second run must be a clean no-op for reference data

    db = TestSession()
    try:
        assert db.query(Instrument).filter_by(name="NIRCam").count() == 1
        assert db.query(Instrument).filter_by(name="MIRI").count() == 1
        assert db.query(Band).filter_by(name="F150W").count() == 1
        assert db.query(Band).filter_by(name="F277W").count() == 1
    finally:
        db.close()

    _cleanup_seeded_rows(TestSession)


def test_tile_and_epoch_roundtrip_with_project_fk(db, user):
    """Tile and Epoch persist and their foreign keys resolve back to the parent objects."""
    project = Project(name="DomainTestProject", user_id=user.id)
    db.add(project)
    db.flush()
    _instrument, band = _make_ref(db)
    tile = _make_tile(db, project)
    epoch = _make_epoch(db, project, tile, band)

    fetched_tile = db.get(Tile, tile.id)
    assert fetched_tile.coord_sys == 2000  # Python-side default applied
    assert fetched_tile.project.id == project.id

    fetched_epoch = db.get(Epoch, epoch.id)
    assert fetched_epoch.project.id == project.id
    assert fetched_epoch.tile.id == tile.id
    assert fetched_epoch.band.id == band.id


def test_q3c_extension_and_index_exist(db):
    """The migration enabled the Q3C extension and built the tile spatial index."""
    ext = db.execute(
        text("SELECT 1 FROM pg_extension WHERE extname = 'q3c'")
    ).fetchone()
    assert ext is not None
    idx = db.execute(
        text("SELECT 1 FROM pg_indexes WHERE indexname = 'ix_tile_q3c'")
    ).fetchone()
    assert idx is not None


def test_level2_image_and_calibration_one_to_one(db):
    """Level2Calibration round-trips, defaults status to PENDING, and back-navigates to its image."""
    instrument, band = _make_ref(db)
    image = _make_image(db, instrument, band)
    cal = _make_calibration(db, image)

    fetched = db.get(Level2Calibration, cal.id)
    assert fetched.status == JobStatus.PENDING  # Python-side default applied
    assert fetched.plate_scale == 0.031
    assert fetched.level2_image.base_filename == "jw001_cal.fits"
    # One-to-one back reference from the immutable image to its calibration.
    assert db.get(Level2Image, image.id).calibration.id == cal.id


def test_level2_image_calibration_is_one_per_image(db):
    """The unique constraint on level2_image_id forbids a second calibration for one image."""
    instrument, band = _make_ref(db)
    image = _make_image(db, instrument, band)
    _make_calibration(db, image)
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            db.add(
                Level2Calibration(
                    level2_image_id=image.id,
                    current_file_ext=".fits",
                    plate_scale=0.062,
                )
            )
            db.flush()


def test_calibration_associates_with_many_tiles_and_epochs(db, user):
    """A single Level2Calibration can belong to multiple Tiles and Epochs via the junction tables."""
    project = Project(name="DomainTestProject", user_id=user.id)
    db.add(project)
    db.flush()
    instrument, band = _make_ref(db)
    tile_a = _make_tile(db, project, name="Tile-A")
    tile_b = _make_tile(db, project, name="Tile-B")
    epoch_a = _make_epoch(db, project, tile_a, band)
    epoch_b = _make_epoch(db, project, tile_b, band)
    cal = _make_calibration(db, _make_image(db, instrument, band))

    cal.tiles.extend([tile_a, tile_b])
    cal.epochs.extend([epoch_a, epoch_b])
    db.flush()

    fetched = db.get(Level2Calibration, cal.id)
    assert {t.id for t in fetched.tiles} == {tile_a.id, tile_b.id}
    assert {e.id for e in fetched.epochs} == {epoch_a.id, epoch_b.id}
    junction_count = db.execute(
        text(
            "SELECT count(*) FROM tile_level2_calibration_association "
            "WHERE level2_calibration_id = :cid"
        ),
        {"cid": cal.id},
    ).scalar()
    assert junction_count == 2


def test_duplicate_tile_association_is_rejected(db, user):
    """The association composite primary key rejects a duplicate tile/calibration pairing."""
    project = Project(name="DomainTestProject", user_id=user.id)
    db.add(project)
    db.flush()
    instrument, band = _make_ref(db)
    tile = _make_tile(db, project)
    cal = _make_calibration(db, _make_image(db, instrument, band))

    db.execute(
        tile_level2_calibration_association.insert().values(
            tile_id=tile.id, level2_calibration_id=cal.id
        )
    )
    db.flush()
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            db.execute(
                tile_level2_calibration_association.insert().values(
                    tile_id=tile.id, level2_calibration_id=cal.id
                )
            )
            db.flush()


def test_level3_mosaic_roundtrip_and_identity_uniqueness(db, user):
    """Level3Mosaic round-trips, and a second mosaic with the same identity tuple is rejected."""
    project = Project(name="DomainTestProject", user_id=user.id)
    db.add(project)
    db.flush()
    instrument, band = _make_ref(db)
    tile = _make_tile(db, project)
    epoch = _make_epoch(db, project, tile, band)

    mosaic = Level3Mosaic(
        filename="mosaic_1.fits",
        target_plate_scale=0.031,
        instrument_id=instrument.id,
        band_id=band.id,
        epoch_id=epoch.id,
        tile_id=tile.id,
        project_id=project.id,
    )
    db.add(mosaic)
    db.flush()

    fetched = db.get(Level3Mosaic, mosaic.id)
    assert fetched.status == JobStatus.PENDING  # Python-side default applied
    assert fetched.tile.id == tile.id
    assert fetched.epoch.id == epoch.id
    assert fetched.job_configuration_id is None

    # Same (instrument, tile, epoch, band, project) tuple -> duplicate rejected.
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            db.add(
                Level3Mosaic(
                    filename="mosaic_2.fits",
                    target_plate_scale=0.062,
                    instrument_id=instrument.id,
                    band_id=band.id,
                    epoch_id=epoch.id,
                    tile_id=tile.id,
                    project_id=project.id,
                )
            )
            db.flush()
