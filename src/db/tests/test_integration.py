"""Integration tests that run against a live PostgreSQL instance.

These tests validate that:
  - Alembic migrations materialize the correct Postgres enum types and tables.
  - SQLAlchemy ORM enum mappings round-trip correctly through the database.
  - Status transitions write and read back the expected Python enum instances.
  - The job_kwargs JSON column stores and retrieves configuration dicts correctly.
"""
from sqlalchemy import text

from src.db.enums import CeleryQueue, JobStatus
from src.db.models import DummyImage, StepDefinition


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


def test_dummy_image_job_kwargs_roundtrip(db):
    config = {"sleep_duration": 7}
    image = DummyImage(status=JobStatus.IN_PROCESS, job_kwargs=config)
    db.add(image)
    db.flush()

    fetched = db.get(DummyImage, image.id)
    assert fetched.job_kwargs == {"sleep_duration": 7}


def test_dummy_image_job_kwargs_nullable(db):
    image = DummyImage(status=JobStatus.PENDING)
    db.add(image)
    db.flush()

    fetched = db.get(DummyImage, image.id)
    assert fetched.job_kwargs is None
