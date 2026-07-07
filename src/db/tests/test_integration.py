"""Integration tests that run against a live PostgreSQL instance.

These tests validate that:
  - Alembic migrations materialize the correct Postgres enum types and tables.
  - SQLAlchemy ORM enum mappings round-trip correctly through the database.
  - Status transitions write and read back the expected Python enum instances.
  - The JobConfiguration table and its relationship to DummyImage round-trip correctly.
"""
from sqlalchemy import text

from src.db.enums import CeleryQueue, JobStatus
from src.db.models import DummyImage, JobConfiguration, StepDefinition


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


def test_step_definition_queue_roundtrip(db):
    step = StepDefinition(
        name="integration_test_step",
        task_name="src.worker.tasks.sleep_and_update_status",
        queue=CeleryQueue.LIGHT,
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


def test_job_configuration_roundtrip(db):
    config = JobConfiguration(
        job_kwargs={"sleep_duration": 7},
        execution_command="diffpype-manage run-dummy --sleep 7",
    )
    db.add(config)
    db.flush()

    fetched = db.get(JobConfiguration, config.id)
    assert fetched.job_kwargs == {"sleep_duration": 7}
    assert fetched.execution_command == "diffpype-manage run-dummy --sleep 7"


def test_dummy_image_job_configuration_relationship(db):
    config = JobConfiguration(
        job_kwargs={"sleep_duration": 3},
        execution_command="diffpype-manage run-dummy --sleep 3",
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


def test_job_configuration_timestamps_populated(db):
    """The TimestampMixin server defaults populate created_at/updated_at on insert."""
    config = JobConfiguration(
        job_kwargs={"sleep_duration": 5},
        execution_command="diffpype-manage run-dummy --sleep 5",
    )
    db.add(config)
    db.flush()
    db.refresh(config)

    assert config.created_at is not None
    assert config.updated_at is not None
