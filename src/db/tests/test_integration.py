"""Integration tests that run against a live PostgreSQL instance.

These tests validate that:
  - Alembic migrations materialize the correct Postgres enum types and tables.
  - SQLAlchemy ORM enum mappings round-trip correctly through the database.
  - Status transitions write and read back the expected Python enum instances.
  - The JobConfiguration table and its relationship to DummyImage round-trip correctly.
"""
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from src.db.enums import CeleryQueue, JobStatus
from src.db.models import DummyImage, JobConfiguration, StepDefinition, User


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
    u = User(username="testuser", email="test@example.com", is_active=True)
    db.add(u)
    db.flush()
    db.refresh(u)

    fetched = db.get(User, u.id)
    assert fetched.username == "testuser"
    assert fetched.email == "test@example.com"
    assert fetched.is_active is True
    assert fetched.created_at is not None
    assert fetched.updated_at is not None


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
        step = db.query(StepDefinition).filter_by(name="dummy_sleep").one_or_none()
        assert step is not None
        assert step.user_id == sysadmin.id
    finally:
        db.close()

    # Committed outside the transactional fixture — must clean up explicitly so the
    # unique constraint on username doesn't bleed into subsequent tests.
    cleanup = TestSession()
    try:
        cleanup.query(StepDefinition).filter_by(name="dummy_sleep").delete()
        cleanup.query(User).filter_by(username="sysadmin").delete()
        cleanup.commit()
    finally:
        cleanup.close()
