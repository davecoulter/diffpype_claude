"""Integration tests that run against a live PostgreSQL instance.

These tests validate that:
  - Alembic migrations materialize the correct Postgres enum types and tables.
  - SQLAlchemy ORM enum mappings round-trip correctly through the database.
  - Status transitions write and read back the expected Python enum instances.
  - The JobConfiguration table and its relationship to tracked entities round-trip correctly.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import astropy.units as u
import pandas as pd
import pytest
from mocpy import MOC
from slugify import slugify
from sqlalchemy import literal, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from src.db.enums import CeleryQueue, JobStatus
from src.db.spatial_types import MOCType
from src.db.models import (
    Band,
    Epoch,
    IngestBatch,
    Instrument,
    JobConfiguration,
    Level2Calibration,
    Level2Image,
    Level3Mosaic,
    Project,
    StepDefinition,
    Tile,
    User,
    epoch_level2_calibration_association,
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


def test_ingest_batch_status_roundtrip(db, user):
    project = _make_project(db, user)
    batch = IngestBatch(
        project_id=project.id, s3_prefix="raw/", status=JobStatus.IN_PROCESS
    )
    db.add(batch)
    db.flush()

    fetched = db.get(IngestBatch, batch.id)
    assert fetched.status == JobStatus.IN_PROCESS
    assert isinstance(fetched.status, JobStatus)

    fetched.status = JobStatus.COMPLETE
    db.flush()

    updated = db.get(IngestBatch, batch.id)
    assert updated.status == JobStatus.COMPLETE


def test_step_definition_queue_roundtrip(db, user):
    step = StepDefinition(
        name="integration_test_step",
        task_name="src.worker.tasks.run_ingest_batch",
        queue=CeleryQueue.LIGHT,
        user_id=user.id,
    )
    db.add(step)
    db.flush()

    fetched = db.get(StepDefinition, step.id)
    assert fetched.queue == CeleryQueue.LIGHT
    assert isinstance(fetched.queue, CeleryQueue)


def test_all_job_status_transitions(db, user):
    """Every status value in the enum can be written to and read from the DB."""
    project = _make_project(db, user)
    for status in JobStatus:
        batch = IngestBatch(project_id=project.id, s3_prefix="raw/", status=status)
        db.add(batch)
        db.flush()
        assert db.get(IngestBatch, batch.id).status == status


def test_job_configuration_roundtrip(db, user):
    config = JobConfiguration(
        job_kwargs={"batch_size": 7},
        execution_command="diffpype-manage ingest --project-id 1 --s3-prefix raw/",
        user_id=user.id,
    )
    db.add(config)
    db.flush()

    fetched = db.get(JobConfiguration, config.id)
    assert fetched.job_kwargs == {"batch_size": 7}
    assert (
        fetched.execution_command
        == "diffpype-manage ingest --project-id 1 --s3-prefix raw/"
    )


def test_ingest_batch_job_configuration_relationship(db, user):
    """IngestBatch's new job_configuration_id FK links to a JobConfiguration (doc 29 §2)."""
    project = _make_project(db, user)
    config = JobConfiguration(
        job_kwargs={"batch_size": 3},
        execution_command="diffpype-manage ingest",
        user_id=user.id,
    )
    batch = IngestBatch(
        project_id=project.id,
        s3_prefix="raw/",
        status=JobStatus.IN_PROCESS,
        job_configuration=config,
    )
    db.add(batch)
    db.flush()

    fetched = db.get(IngestBatch, batch.id)
    assert fetched.job_configuration_id == config.id
    assert fetched.job_configuration.job_kwargs == {"batch_size": 3}


def test_ingest_batch_job_configuration_nullable(db, user):
    project = _make_project(db, user)
    batch = IngestBatch(
        project_id=project.id, s3_prefix="raw/", status=JobStatus.PENDING
    )
    db.add(batch)
    db.flush()

    fetched = db.get(IngestBatch, batch.id)
    assert fetched.job_configuration_id is None
    assert fetched.job_configuration is None


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
        task_name="src.worker.tasks.run_ingest_batch",
        queue=CeleryQueue.LIGHT,
        user_id=user.id,
    )
    db.add(step)
    db.flush()

    fetched = db.get(StepDefinition, step.id)
    assert fetched.user_id == user.id
    assert fetched.user.username == user.username


def test_sysadmin_seeding_creates_sysadmin_user(mocker, test_engine):
    """seed_step_definitions upserts a sysadmin User with a hashed password."""
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
    from sqlalchemy_celery_beat.models import IntervalSchedule, PeriodicTask

    cleanup = TestSession()
    try:
        sysadmin_id = cleanup.query(User.id).filter_by(username="sysadmin").scalar()
        if sysadmin_id is not None:
            cleanup.query(JobConfiguration).filter_by(user_id=sysadmin_id).delete()
        cleanup.query(User).filter_by(username="sysadmin").delete()
        cleanup.query(Instrument).filter(
            Instrument.name.in_(["NIRCam", "MIRI"])
        ).delete(synchronize_session=False)
        cleanup.query(Band).filter(Band.name.in_(["F150W", "F277W"])).delete(
            synchronize_session=False
        )
        # seed_step_definitions also seeds the Beat schedules (doc 30 §4), committed
        # outside the fixture. Delete PeriodicTask before IntervalSchedule (the
        # former references the latter via the polymorphic schedule association).
        cleanup.query(PeriodicTask).delete()
        cleanup.query(IntervalSchedule).delete()
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
        healpix_index=(ra, decl),
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
        healpix_index=(150.12, 2.31),
        instrument_id=instrument.id,
        band_id=band.id,
    )
    db.add(img)
    db.flush()
    return img


def _make_calibration(db, image, project, plate_scale=0.031):
    cal = Level2Calibration(
        level2_image_id=image.id,
        project_id=project.id,
        current_file_ext=".fits",
        plate_scale=plate_scale,
    )
    db.add(cal)
    db.flush()
    return cal


def _make_project(db, user, name="DomainTestProject"):
    project = Project(name=name, slug=slugify(name), user_id=user.id)
    db.add(project)
    db.flush()
    return project


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


def test_project_slug_is_unique(db, user):
    """A duplicate Project slug is rejected by the database."""
    db.add(Project(name="Same Name", slug="same-name", user_id=user.id))
    db.flush()
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            db.add(Project(name="Same Name Again", slug="same-name", user_id=user.id))
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
    project = _make_project(db, user)
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


def test_level2_calibration_roundtrip_and_back_reference(db, user):
    """Level2Calibration round-trips, defaults status to PENDING, and its image lists it back."""
    project = _make_project(db, user)
    instrument, band = _make_ref(db)
    image = _make_image(db, instrument, band)
    cal = _make_calibration(db, image, project)

    fetched = db.get(Level2Calibration, cal.id)
    assert fetched.status == JobStatus.PENDING  # Python-side default applied
    assert fetched.plate_scale == 0.031
    assert fetched.level2_image.base_filename == "jw001_cal.fits"
    assert fetched.project.id == project.id
    # The immutable image now back-references a list of per-project calibrations.
    assert [c.id for c in db.get(Level2Image, image.id).calibrations] == [cal.id]


def test_same_image_different_projects_allows_two_calibrations(db, user):
    """One raw image can carry a distinct Level2Calibration per Project."""
    project_a = _make_project(db, user, name="ProjectA")
    project_b = _make_project(db, user, name="ProjectB")
    instrument, band = _make_ref(db)
    image = _make_image(db, instrument, band)

    cal_a = _make_calibration(db, image, project_a, plate_scale=0.031)
    cal_b = _make_calibration(db, image, project_b, plate_scale=0.062)

    fetched_image = db.get(Level2Image, image.id)
    assert {c.id for c in fetched_image.calibrations} == {cal_a.id, cal_b.id}
    assert {c.project_id for c in fetched_image.calibrations} == {
        project_a.id,
        project_b.id,
    }


def test_same_image_same_project_calibration_is_rejected(db, user):
    """The composite (level2_image_id, project_id) unique forbids two calibrations per pair."""
    project = _make_project(db, user)
    instrument, band = _make_ref(db)
    image = _make_image(db, instrument, band)
    _make_calibration(db, image, project)
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            db.add(
                Level2Calibration(
                    level2_image_id=image.id,
                    project_id=project.id,
                    current_file_ext=".fits",
                    plate_scale=0.062,
                )
            )
            db.flush()


def test_base_filename_is_unique(db):
    """A duplicate Level2Image base_filename is rejected by the database."""
    instrument, band = _make_ref(db)
    _make_image(db, instrument, band, base_filename="jw_dupe_cal.fits")
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            _make_image(db, instrument, band, base_filename="jw_dupe_cal.fits")


def test_footprint_moc_roundtrip_fidelity(db, user):
    """A MOC footprint stored via MOCType reads back covering the identical sky region."""
    project = _make_project(db, user)
    instrument, band = _make_ref(db)
    image = _make_image(db, instrument, band)
    cal = _make_calibration(db, image, project)

    original = MOC.from_cone(
        lon=150.12 * u.deg, lat=2.31 * u.deg, radius=0.3 * u.deg, max_depth=9
    )
    cal.footprint = original
    db.flush()
    db.expire(cal)

    reloaded = db.get(Level2Calibration, cal.id).footprint
    assert isinstance(reloaded, MOC)
    # Coverage-equivalence, not object identity: normalizing to depth 29 preserves the
    # exact sky region (equal sky_fraction, empty symmetric difference) but not the
    # original authoring order.
    assert reloaded.sky_fraction == original.sky_fraction
    assert original.symmetric_difference(reloaded).empty()


def test_footprint_none_and_empty_and_update_paths(db, user):
    """None persists as NULL, an empty MOC round-trips empty, and MOC<->None updates never crash."""
    project = _make_project(db, user)
    instrument, band = _make_ref(db)
    image = _make_image(db, instrument, band)
    cal = _make_calibration(db, image, project)

    # Default (unset) footprint is NULL.
    assert db.get(Level2Calibration, cal.id).footprint is None

    # Regression for the mocpy __eq__(None) crash in ORM change detection:
    # each of these transitions triggers compare_values(old, new).
    moc = MOC.from_cone(lon=10 * u.deg, lat=20 * u.deg, radius=0.2 * u.deg, max_depth=8)
    cal.footprint = moc
    db.flush()
    db.expire(cal)
    assert db.get(Level2Calibration, cal.id).footprint.sky_fraction == moc.sky_fraction

    cal.footprint = None
    db.flush()
    db.expire(cal)
    assert db.get(Level2Calibration, cal.id).footprint is None

    cal.footprint = MOC.new_empty(29)
    db.flush()
    db.expire(cal)
    assert db.get(Level2Calibration, cal.id).footprint.empty()

    # Update one loaded MOC to a coverage-different MOC: exercises the MOC-vs-MOC
    # branch of compare_values (old value already materialized as a MOC).
    loaded = db.get(Level2Calibration, cal.id)
    assert loaded.footprint.empty()
    loaded.footprint = moc
    db.flush()
    db.expire(loaded)
    assert db.get(Level2Calibration, cal.id).footprint.sky_fraction == moc.sky_fraction


def test_footprint_overlap_query_returns_only_spatial_matches(db, user):
    """A native `&&` multirange overlap query returns only footprints covering the probe region.

    This is the capability GitHub issue #26 targets: spatial matching expressed as an
    indexed range query in the database, not deserialize-then-compute in Python. It is
    the query that the doc-28 ingest/spatial-match tooling will build on.
    """
    project = _make_project(db, user)
    instrument, band = _make_ref(db)
    cal_near = _make_calibration(
        db, _make_image(db, instrument, band, base_filename="near.fits"), project
    )
    cal_far = _make_calibration(
        db, _make_image(db, instrument, band, base_filename="far.fits"), project
    )
    cal_near.footprint = MOC.from_cone(
        lon=10 * u.deg, lat=20 * u.deg, radius=0.3 * u.deg, max_depth=9
    )
    cal_far.footprint = MOC.from_cone(
        lon=200 * u.deg, lat=-40 * u.deg, radius=0.3 * u.deg, max_depth=9
    )
    db.flush()

    # A probe that overlaps only the "near" footprint.
    probe = MOC.from_cone(
        lon=10.1 * u.deg, lat=20.0 * u.deg, radius=0.3 * u.deg, max_depth=9
    )
    stmt = (
        select(Level2Calibration.id)
        .where(Level2Calibration.footprint.op("&&")(literal(probe, type_=MOCType)))
        .order_by(Level2Calibration.id)
    )
    hits = [row[0] for row in db.execute(stmt)]
    assert hits == [cal_near.id]

    # A probe far from both returns nothing.
    empty_probe = MOC.from_cone(
        lon=100 * u.deg, lat=0 * u.deg, radius=0.3 * u.deg, max_depth=9
    )
    empty_stmt = select(Level2Calibration.id).where(
        Level2Calibration.footprint.op("&&")(literal(empty_probe, type_=MOCType))
    )
    assert db.execute(empty_stmt).all() == []


def test_footprint_contains_healpix_index_point_query(db, user):
    """A native `@>` containment query returns only point-index rows inside a footprint.

    This is the cross-table capability doc 29 §2 enables: `footprint @> healpix_index`
    (int8multirange @> int8range) is an indexed containment test performed in the
    database, not a Python-side point-in-polygon computation. q3c handles proximity
    search on the raw ra/decl; the healpix_index handles containment against another
    table's footprint.
    """
    project = _make_project(db, user)
    instrument, band = _make_ref(db)

    # A tile whose footprint covers a small cone centered on the "inside" image.
    tile = _make_tile(db, project)  # ra/decl 150.12/2.31, healpix_index populated
    tile.footprint = MOC.from_cone(
        lon=150.12 * u.deg, lat=2.31 * u.deg, radius=0.3 * u.deg, max_depth=12
    )
    # One image point inside the footprint (same coords as the tile center), one far away.
    img_inside = _make_image(db, instrument, band, base_filename="inside.fits")
    img_outside = Level2Image(
        base_filename="outside.fits",
        ra=200.0,
        decl=-40.0,
        exp_time=1.0,
        target_name="OUT",
        obs_start=_utc(2024, 1, 1),
        healpix_index=(200.0, -40.0),
        instrument_id=instrument.id,
        band_id=band.id,
    )
    db.add(img_outside)
    db.flush()

    stmt = (
        select(Level2Image.id)
        .select_from(Tile)
        .join(Level2Image, Tile.footprint.op("@>")(Level2Image.healpix_index))
        .where(Tile.id == tile.id)
        .order_by(Level2Image.id)
    )
    hits = [row[0] for row in db.execute(stmt)]
    assert hits == [img_inside.id]


def test_calibration_associates_with_many_tiles_and_epochs(db, user):
    """A single Level2Calibration can belong to multiple Tiles and Epochs via the junction tables."""
    project = _make_project(db, user)
    instrument, band = _make_ref(db)
    tile_a = _make_tile(db, project, name="Tile-A")
    tile_b = _make_tile(db, project, name="Tile-B")
    epoch_a = _make_epoch(db, project, tile_a, band)
    epoch_b = _make_epoch(db, project, tile_b, band)
    cal = _make_calibration(db, _make_image(db, instrument, band), project)

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
    project = _make_project(db, user)
    instrument, band = _make_ref(db)
    tile = _make_tile(db, project)
    cal = _make_calibration(db, _make_image(db, instrument, band), project)

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
    project = _make_project(db, user)
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


def test_create_tiles_persists_and_associates_overlapping_calibrations(test_engine):
    """create_tiles bulk-inserts Tile rows and links only spatially-overlapping calibrations.

    Runs on its own session for the same reason as the ingest bulk-upsert test:
    create_tiles calls db.commit() internally.
    """
    from src.services.tile_service import create_tiles

    TestSession = sessionmaker(bind=test_engine)
    db = TestSession()
    try:
        user = User(
            username="tileserviceowner",
            email="tileserviceowner@diffpype.local",
            is_active=True,
            hashed_password="dummy_hash_for_testing",
        )
        db.add(user)
        db.flush()
        project = Project(
            name="TileServiceProject", slug="tile-service-project", user_id=user.id
        )
        db.add(project)
        instrument = Instrument(name="NIRCam-tilesvc")
        band = Band(name="F150W-tilesvc", central_lambda=1.501)
        db.add_all([instrument, band])
        db.flush()

        def _make_cal(base_filename, ra, decl):
            image = Level2Image(
                base_filename=base_filename,
                ra=ra,
                decl=decl,
                exp_time=1.0,
                target_name="TILESVC-TARGET",
                obs_start=_utc(2024, 1, 1),
                healpix_index=(ra, decl),
                instrument_id=instrument.id,
                band_id=band.id,
            )
            db.add(image)
            db.flush()
            cal = Level2Calibration(
                level2_image_id=image.id,
                project_id=project.id,
                current_file_ext=".fits",
                plate_scale=0.03,
                footprint=MOC.from_cone(
                    lon=ra * u.deg, lat=decl * u.deg, radius=0.05 * u.deg, max_depth=12
                ),
            )
            db.add(cal)
            db.flush()
            return cal

        near_cal = _make_cal("tile_svc_near.fits", 10.0, 20.0)
        _make_cal("tile_svc_far.fits", 200.0, -40.0)  # must NOT be associated
        db.commit()

        tile_footprint = MOC.from_cone(
            lon=10 * u.deg, lat=20 * u.deg, radius=0.1 * u.deg, max_depth=10
        )
        created = create_tiles(
            db,
            project.id,
            [
                {
                    "name": "AssocTile",
                    "ra": 10.0,
                    "decl": 20.0,
                    "delta_ra": 0.2,
                    "delta_decl": 0.2,
                    "footprint": tile_footprint,
                }
            ],
        )

        assert len(created) == 1
        tile = created[0]
        assert tile.id is not None
        assoc_ids = {
            row.level2_calibration_id
            for row in db.execute(
                text(
                    "SELECT level2_calibration_id FROM tile_level2_calibration_association "
                    "WHERE tile_id = :tid"
                ),
                {"tid": tile.id},
            ).all()
        }
        assert assoc_ids == {near_cal.id}
    finally:
        db.execute(
            text(
                "DELETE FROM tile_level2_calibration_association "
                "WHERE tile_id IN (SELECT id FROM tiles WHERE project_id IN "
                "(SELECT id FROM projects WHERE slug = 'tile-service-project'))"
            )
        )
        db.query(Tile).filter(
            Tile.project_id.in_(
                db.query(Project.id).filter_by(slug="tile-service-project")
            )
        ).delete(synchronize_session=False)
        db.query(Level2Calibration).filter(
            Level2Calibration.project_id.in_(
                db.query(Project.id).filter_by(slug="tile-service-project")
            )
        ).delete(synchronize_session=False)
        db.query(Level2Image).filter(
            Level2Image.base_filename.in_(["tile_svc_near.fits", "tile_svc_far.fits"])
        ).delete(synchronize_session=False)
        db.query(Project).filter_by(slug="tile-service-project").delete()
        db.query(Band).filter_by(name="F150W-tilesvc").delete()
        db.query(Instrument).filter_by(name="NIRCam-tilesvc").delete()
        db.query(User).filter_by(username="tileserviceowner").delete()
        db.commit()
        db.close()


def test_create_epochs_persists_and_associates_calibrations_in_mjd_range(test_engine):
    """create_epochs bulk-inserts Epoch rows and links only calibrations whose MJD is in range.

    Runs on its own session for the same reason as the other service-layer
    integration tests: create_epochs calls db.commit() internally.
    """
    from src.services.epoch_service import create_epochs

    TestSession = sessionmaker(bind=test_engine)
    db = TestSession()
    try:
        user = User(
            username="epochserviceowner",
            email="epochserviceowner@diffpype.local",
            is_active=True,
            hashed_password="dummy_hash_for_testing",
        )
        db.add(user)
        db.flush()
        project = Project(
            name="EpochServiceProject", slug="epoch-service-project", user_id=user.id
        )
        db.add(project)
        instrument = Instrument(name="NIRCam-epochsvc")
        band = Band(name="F150W-epochsvc", central_lambda=1.501)
        db.add_all([instrument, band])
        db.flush()
        tile = Tile(
            name="EpochSvcTile",
            ra=10.0,
            decl=20.0,
            delta_ra=0.2,
            delta_decl=0.2,
            healpix_index=(10.0, 20.0),
            coord_sys=2000,
            project_id=project.id,
        )
        other_tile = Tile(
            name="EpochSvcOtherTile",
            ra=200.0,
            decl=-40.0,
            delta_ra=0.2,
            delta_decl=0.2,
            healpix_index=(200.0, -40.0),
            coord_sys=2000,
            project_id=project.id,
        )
        db.add_all([tile, other_tile])
        db.flush()

        def _make_cal(base_filename, mjd_avg, associated_tile):
            image = Level2Image(
                base_filename=base_filename,
                ra=10.0,
                decl=20.0,
                exp_time=1.0,
                mjd_avg=mjd_avg,
                target_name="EPOCHSVC-TARGET",
                obs_start=_utc(2024, 1, 1),
                healpix_index=(10.0, 20.0),
                instrument_id=instrument.id,
                band_id=band.id,
            )
            db.add(image)
            db.flush()
            cal = Level2Calibration(
                level2_image_id=image.id,
                project_id=project.id,
                current_file_ext=".fits",
                plate_scale=0.03,
            )
            db.add(cal)
            db.flush()
            db.execute(
                tile_level2_calibration_association.insert().values(
                    tile_id=associated_tile.id, level2_calibration_id=cal.id
                )
            )
            return cal

        in_range_cal = _make_cal("epoch_svc_in_range.fits", 60300.5, tile)
        _make_cal(
            "epoch_svc_out_of_range.fits", 61000.0, tile
        )  # right tile, wrong MJD -> must NOT be associated
        _make_cal(
            "epoch_svc_wrong_tile.fits", 60300.6, other_tile
        )  # right MJD, wrong tile -> must NOT be associated
        db.commit()

        created = create_epochs(
            db,
            project.id,
            [
                {
                    "start_date": _utc(2024, 1, 1),
                    "end_date": _utc(2024, 1, 2),
                    "start_mjd": 60300.0,
                    "end_mjd": 60301.0,
                    "tile_id": tile.id,
                    "band_id": band.id,
                }
            ],
        )

        assert len(created) == 1
        epoch = created[0]
        assert epoch.id is not None
        assoc_ids = {
            row.level2_calibration_id
            for row in db.execute(
                text(
                    "SELECT level2_calibration_id FROM epoch_level2_calibration_association "
                    "WHERE epoch_id = :eid"
                ),
                {"eid": epoch.id},
            ).all()
        }
        assert assoc_ids == {in_range_cal.id}
    finally:
        db.execute(
            text(
                "DELETE FROM epoch_level2_calibration_association "
                "WHERE epoch_id IN (SELECT id FROM epochs WHERE project_id IN "
                "(SELECT id FROM projects WHERE slug = 'epoch-service-project'))"
            )
        )
        db.execute(
            text(
                "DELETE FROM tile_level2_calibration_association "
                "WHERE tile_id IN (SELECT id FROM tiles WHERE project_id IN "
                "(SELECT id FROM projects WHERE slug = 'epoch-service-project'))"
            )
        )
        db.query(Epoch).filter(
            Epoch.project_id.in_(
                db.query(Project.id).filter_by(slug="epoch-service-project")
            )
        ).delete(synchronize_session=False)
        db.query(Level2Calibration).filter(
            Level2Calibration.project_id.in_(
                db.query(Project.id).filter_by(slug="epoch-service-project")
            )
        ).delete(synchronize_session=False)
        db.query(Level2Image).filter(
            Level2Image.base_filename.in_(
                [
                    "epoch_svc_in_range.fits",
                    "epoch_svc_out_of_range.fits",
                    "epoch_svc_wrong_tile.fits",
                ]
            )
        ).delete(synchronize_session=False)
        db.query(Tile).filter(
            Tile.name.in_(["EpochSvcTile", "EpochSvcOtherTile"])
        ).delete(synchronize_session=False)
        db.query(Project).filter_by(slug="epoch-service-project").delete()
        db.query(Band).filter_by(name="F150W-epochsvc").delete()
        db.query(Instrument).filter_by(name="NIRCam-epochsvc").delete()
        db.query(User).filter_by(username="epochserviceowner").delete()
        db.commit()
        db.close()


def test_create_mosaic_computes_footprint_and_barycenter_from_constituent_calibrations(
    test_engine, mocker
):
    """create_mosaic unions footprints of calibrations linked via BOTH tile and epoch M2M tables.

    Runs on its own session for the same reason as the other service-layer
    integration tests: create_mosaic calls db.commit() internally. Mocks the
    Celery dispatch: worker_heavy is a real running container consuming this
    queue, so an un-mocked .delay() risks a race where it flips the mosaic's
    status before this test's assertions read it — the DB footprint/barycenter
    computation is what this test verifies, not the dispatch itself (already
    covered by unit tests).
    """
    from src.services.mosaic_service import create_mosaic

    mocker.patch(
        "src.worker.tasks.run_mosaic_drizzle.delay",
        return_value=MagicMock(id="fake-mosaic-task-id"),
    )

    TestSession = sessionmaker(bind=test_engine)
    db = TestSession()
    try:
        user = User(
            username="mosaicserviceowner",
            email="mosaicserviceowner@diffpype.local",
            is_active=True,
            hashed_password="dummy_hash_for_testing",
        )
        db.add(user)
        db.flush()
        project = Project(
            name="MosaicServiceProject", slug="mosaic-service-project", user_id=user.id
        )
        db.add(project)
        instrument = Instrument(name="NIRCam-mosaicsvc")
        band = Band(name="F150W-mosaicsvc", central_lambda=1.501)
        other_band = Band(name="F277W-mosaicsvc", central_lambda=2.776)
        db.add_all([instrument, band, other_band])
        db.flush()
        tile = Tile(
            name="MosaicSvcTile",
            ra=10.0,
            decl=20.0,
            delta_ra=0.5,
            delta_decl=0.5,
            healpix_index=(10.0, 20.0),
            coord_sys=2000,
            project_id=project.id,
        )
        db.add(tile)
        db.flush()
        epoch = Epoch(
            start_date=_utc(2024, 1, 1),
            end_date=_utc(2024, 1, 2),
            start_mjd=60300.0,
            end_mjd=60301.0,
            project_id=project.id,
            tile_id=tile.id,
            band_id=band.id,
        )
        db.add(epoch)
        db.flush()

        def _make_associated_cal(base_filename, ra, band_row):
            image = Level2Image(
                base_filename=base_filename,
                ra=ra,
                decl=20.0,
                exp_time=1.0,
                mjd_avg=60300.5,
                target_name="MOSAICSVC-TARGET",
                obs_start=_utc(2024, 1, 1),
                healpix_index=(ra, 20.0),
                instrument_id=instrument.id,
                band_id=band_row.id,
            )
            db.add(image)
            db.flush()
            cal = Level2Calibration(
                level2_image_id=image.id,
                project_id=project.id,
                current_file_ext=".fits",
                plate_scale=0.03,
                footprint=MOC.from_cone(
                    lon=ra * u.deg, lat=20.0 * u.deg, radius=0.05 * u.deg, max_depth=12
                ),
            )
            db.add(cal)
            db.flush()
            db.execute(
                tile_level2_calibration_association.insert().values(
                    tile_id=tile.id, level2_calibration_id=cal.id
                )
            )
            db.execute(
                epoch_level2_calibration_association.insert().values(
                    epoch_id=epoch.id, level2_calibration_id=cal.id
                )
            )
            return cal

        _make_associated_cal("mosaic_svc_a.fits", 10.0, band)
        _make_associated_cal("mosaic_svc_b.fits", 10.05, band)
        # Right tile+epoch, wrong band -> must NOT contribute to the union.
        _make_associated_cal("mosaic_svc_wrong_band.fits", 50.0, other_band)
        db.commit()

        job_id, mosaic_id = create_mosaic(
            db,
            project.id,
            tile.id,
            epoch.id,
            band.id,
            instrument.id,
            filename="mosaic_svc.fits",
            target_plate_scale=0.03,
        )

        assert job_id
        mosaic = db.get(Level3Mosaic, mosaic_id)
        assert mosaic.footprint is not None
        assert mosaic.ra == pytest.approx(10.025, abs=0.1)
        assert mosaic.decl == pytest.approx(20.0, abs=0.1)
        # healpix_index populated from the computed barycenter (doc 29 §2).
        from src.db.spatial_types import _point_to_depth29_cell

        assert mosaic.healpix_index == _point_to_depth29_cell(mosaic.ra, mosaic.decl)
        assert mosaic.status == JobStatus.PENDING
    finally:
        db.execute(
            text(
                "DELETE FROM epoch_level2_calibration_association "
                "WHERE epoch_id IN (SELECT id FROM epochs WHERE project_id IN "
                "(SELECT id FROM projects WHERE slug = 'mosaic-service-project'))"
            )
        )
        db.execute(
            text(
                "DELETE FROM tile_level2_calibration_association "
                "WHERE tile_id IN (SELECT id FROM tiles WHERE project_id IN "
                "(SELECT id FROM projects WHERE slug = 'mosaic-service-project'))"
            )
        )
        db.query(Level3Mosaic).filter(
            Level3Mosaic.project_id.in_(
                db.query(Project.id).filter_by(slug="mosaic-service-project")
            )
        ).delete(synchronize_session=False)
        db.query(Epoch).filter(
            Epoch.project_id.in_(
                db.query(Project.id).filter_by(slug="mosaic-service-project")
            )
        ).delete(synchronize_session=False)
        db.query(Level2Calibration).filter(
            Level2Calibration.project_id.in_(
                db.query(Project.id).filter_by(slug="mosaic-service-project")
            )
        ).delete(synchronize_session=False)
        db.query(Level2Image).filter(
            Level2Image.base_filename.in_(
                [
                    "mosaic_svc_a.fits",
                    "mosaic_svc_b.fits",
                    "mosaic_svc_wrong_band.fits",
                ]
            )
        ).delete(synchronize_session=False)
        db.query(Tile).filter_by(name="MosaicSvcTile").delete()
        db.query(Project).filter_by(slug="mosaic-service-project").delete()
        db.query(Band).filter(
            Band.name.in_(["F150W-mosaicsvc", "F277W-mosaicsvc"])
        ).delete(synchronize_session=False)
        db.query(Instrument).filter_by(name="NIRCam-mosaicsvc").delete()
        # create_mosaic now commits a JobConfiguration referencing this user
        # (doc 30 §3); it must be deleted before the user or the FK blocks it.
        db.query(JobConfiguration).filter(
            JobConfiguration.user_id.in_(
                db.query(User.id).filter_by(username="mosaicserviceowner")
            )
        ).delete(synchronize_session=False)
        db.query(User).filter_by(username="mosaicserviceowner").delete()
        db.commit()
        db.close()


def test_bulk_upsert_images_and_calibrations_is_idempotent(test_engine):
    """A real Core bulk upsert: first call inserts, an identical second call is a safe no-op.

    Runs on its own session (not the transactional `db` fixture) because
    bulk_upsert_images_and_calibrations calls db.commit() internally, which
    would otherwise end the fixture's outer transaction early. Committed rows
    are explicitly deleted at the end per the integration-test isolation rule.
    """
    from src.services.ingest_service import bulk_upsert_images_and_calibrations

    TestSession = sessionmaker(bind=test_engine)
    db = TestSession()
    try:
        user = User(
            username="bulkupsertowner",
            email="bulkupsertowner@diffpype.local",
            is_active=True,
            hashed_password="dummy_hash_for_testing",
        )
        db.add(user)
        db.flush()
        project = Project(
            name="BulkUpsertProject", slug="bulk-upsert-project", user_id=user.id
        )
        db.add(project)
        instrument = Instrument(name="NIRCam-bulk")
        band = Band(name="F150W-bulk", central_lambda=1.501)
        db.add_all([instrument, band])
        db.flush()
        db.commit()

        moc = MOC.from_cone(
            lon=10 * u.deg, lat=20 * u.deg, radius=0.01 * u.deg, max_depth=10
        )
        df = pd.DataFrame(
            [
                {
                    "base_filename": "bulk_upsert_test_001.fits",
                    "current_file_ext": ".fits",
                    "ra": 10.0,
                    "decl": 20.0,
                    "exp_time": 100.0,
                    "mjd_avg": 60300.0,
                    "target_name": "BULKTEST",
                    "obs_start": _utc(2024, 1, 1),
                    "instrument_name": "NIRCam-bulk",
                    "band_name": "F150W-bulk",
                    "plate_scale": 0.03,
                    "footprint": moc,
                }
            ]
        )

        count_first = bulk_upsert_images_and_calibrations(db, project.id, df)
        assert count_first == 1

        image = (
            db.query(Level2Image)
            .filter_by(base_filename="bulk_upsert_test_001.fits")
            .one()
        )
        cal = (
            db.query(Level2Calibration)
            .filter_by(level2_image_id=image.id, project_id=project.id)
            .one()
        )
        assert cal.plate_scale == 0.03
        assert cal.status == JobStatus.COMPLETE
        # healpix_index is populated from the row's ra/decl (doc 29 §2, NOT NULL).
        from src.db.spatial_types import _point_to_depth29_cell

        assert image.healpix_index == _point_to_depth29_cell(10.0, 20.0)

        count_second = bulk_upsert_images_and_calibrations(db, project.id, df)
        assert (
            count_second == 1
        )  # still "processed" 1 df row, but persisted no duplicate
        assert (
            db.query(Level2Image)
            .filter_by(base_filename="bulk_upsert_test_001.fits")
            .count()
            == 1
        )
        assert (
            db.query(Level2Calibration)
            .filter_by(level2_image_id=image.id, project_id=project.id)
            .count()
            == 1
        )
    finally:
        db.query(Level2Calibration).filter(
            Level2Calibration.project_id.in_(
                db.query(Project.id).filter_by(slug="bulk-upsert-project")
            )
        ).delete(synchronize_session=False)
        db.query(Level2Image).filter_by(
            base_filename="bulk_upsert_test_001.fits"
        ).delete()
        db.query(Project).filter_by(slug="bulk-upsert-project").delete()
        db.query(Band).filter_by(name="F150W-bulk").delete()
        db.query(Instrument).filter_by(name="NIRCam-bulk").delete()
        db.query(User).filter_by(username="bulkupsertowner").delete()
        db.commit()
        db.close()


# --- Operational services (doc 30) ---


def test_seeding_creates_beat_schedules(mocker, test_engine):
    """seed_step_definitions seeds the sync/reconcile Beat schedules idempotently."""
    from sqlalchemy_celery_beat.models import PeriodicTask

    from src.db.seed import seed_step_definitions

    TestSession = sessionmaker(bind=test_engine)
    mocker.patch("src.db.seed.SessionLocal", side_effect=TestSession)

    seed_step_definitions()

    db = TestSession()
    try:
        names = {t.name for t in db.query(PeriodicTask).all()}
        assert "sync-staging-cron" in names
        assert "reconcile-stuck-jobs-cron" in names
        # A second seed must not duplicate the schedules.
        seed_step_definitions()
        assert db.query(PeriodicTask).count() == 2
    finally:
        db.close()

    _cleanup_seeded_rows(TestSession)


def test_reconcile_stuck_jobs_fails_stale_in_process_records(test_engine):
    """Real-DB watchdog sweep across both tracked entity types + a per-job override.

    Own session (reconcile_stuck_jobs commits internally), with explicit cleanup
    per the integration-test isolation rule.
    """
    from src.services.job_service import reconcile_stuck_jobs

    TestSession = sessionmaker(bind=test_engine)
    db = TestSession()
    user = project = None
    try:
        user = User(
            username="watchdogowner",
            email="watchdogowner@diffpype.local",
            is_active=True,
            hashed_password="dummy_hash_for_testing",
        )
        db.add(user)
        db.flush()
        project = _make_project(db, user, name="WatchdogProject")
        instrument, band = _make_ref(db, "NIRCam-wd", "F150W-wd")
        tile = _make_tile(db, project, name="WD-Tile")
        epoch = _make_epoch(db, project, tile, band)

        stale_batch = IngestBatch(
            project_id=project.id, s3_prefix="raw/", status=JobStatus.IN_PROCESS
        )
        fresh_batch = IngestBatch(
            project_id=project.id, s3_prefix="raw/", status=JobStatus.IN_PROCESS
        )
        override_config = JobConfiguration(
            user_id=user.id,
            task_name="src.worker.tasks.run_ingest_batch",
            job_kwargs={"staleness_timeout_seconds": 60},
        )
        db.add(override_config)
        db.flush()
        override_batch = IngestBatch(
            project_id=project.id,
            s3_prefix="raw/",
            status=JobStatus.IN_PROCESS,
            job_configuration_id=override_config.id,
        )
        stale_mosaic = Level3Mosaic(
            filename="wd.fits",
            target_plate_scale=0.03,
            instrument_id=instrument.id,
            band_id=band.id,
            epoch_id=epoch.id,
            tile_id=tile.id,
            project_id=project.id,
            status=JobStatus.IN_PROCESS,
        )
        db.add_all([stale_batch, fresh_batch, override_batch, stale_mosaic])
        db.commit()

        # updated_at is server-managed; force the stale rows' clocks into the past.
        db.execute(
            text(
                "UPDATE ingest_batches SET updated_at = now() - interval '2 hours' "
                "WHERE id = :i"
            ).bindparams(i=stale_batch.id)
        )
        # override_batch: aged 120s -> survives the 3600s global default, but the
        # per-job 60s override makes it stale.
        db.execute(
            text(
                "UPDATE ingest_batches SET updated_at = now() - interval '120 seconds' "
                "WHERE id = :i"
            ).bindparams(i=override_batch.id)
        )
        db.execute(
            text(
                "UPDATE level3_mosaics SET updated_at = now() - interval '2 hours' "
                "WHERE id = :i"
            ).bindparams(i=stale_mosaic.id)
        )
        db.commit()

        reconciled = reconcile_stuck_jobs(db, staleness_timeout_seconds=3600)

        for row in (stale_batch, fresh_batch, override_batch, stale_mosaic):
            db.refresh(row)
        assert stale_batch.status == JobStatus.FAILED
        assert fresh_batch.status == JobStatus.IN_PROCESS
        assert override_batch.status == JobStatus.FAILED
        assert stale_mosaic.status == JobStatus.FAILED
        reconciled_ids = {(r["entity"], r["id"]) for r in reconciled}
        assert ("IngestBatch", stale_batch.id) in reconciled_ids
        assert ("Level3Mosaic", stale_mosaic.id) in reconciled_ids
    finally:
        if project is not None:
            db.query(Level3Mosaic).filter_by(project_id=project.id).delete(
                synchronize_session=False
            )
            db.query(IngestBatch).filter_by(project_id=project.id).delete(
                synchronize_session=False
            )
            db.query(Epoch).filter_by(project_id=project.id).delete(
                synchronize_session=False
            )
            db.query(Tile).filter_by(project_id=project.id).delete(
                synchronize_session=False
            )
            db.query(Project).filter_by(id=project.id).delete()
        if user is not None:
            db.query(JobConfiguration).filter_by(user_id=user.id).delete(
                synchronize_session=False
            )
            db.query(User).filter_by(id=user.id).delete()
        db.query(Band).filter_by(name="F150W-wd").delete()
        db.query(Instrument).filter_by(name="NIRCam-wd").delete()
        db.commit()
        db.close()
