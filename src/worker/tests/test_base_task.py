from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import OperationalError as SAOperationalError

from src.core.config import settings
from src.db.enums import JobStatus
from src.worker.base_task import NOT_TRACKED, DiffpypeTask, TimeLimitedTask


def test_retryable_exceptions_are_configured():
    """Transient I/O, network, and DB connection errors must trigger automatic retries."""
    for exc_type in (
        IOError,
        OSError,
        ConnectionError,
        TimeoutError,
        SAOperationalError,
    ):
        assert exc_type in DiffpypeTask.autoretry_for


def test_programming_errors_are_not_retried():
    """Logic errors must fail immediately without consuming retry budget."""
    for exc_type in (ValueError, TypeError, KeyError):
        assert exc_type not in DiffpypeTask.autoretry_for


def test_retry_limits_match_settings():
    assert DiffpypeTask.max_retries == settings.celery_task_max_retries
    assert DiffpypeTask.default_retry_delay == settings.celery_task_retry_delay


def test_on_failure_dispatches_to_dlq(mocker):
    """Permanently failed tasks must be routed to the dead_letter queue."""
    mock_dlq = mocker.patch("src.worker.tasks.dlq_dump")

    task = DiffpypeTask()
    task.name = "src.worker.tasks.some_task"
    task.on_failure(RuntimeError("boom"), "task-123", (7,), {"k": "v"}, None)

    mock_dlq.apply_async.assert_called_once_with(
        kwargs={
            "failed_task_name": "src.worker.tasks.some_task",
            "task_kwargs": {"k": "v"},
            "error_msg": "boom",
        },
        queue="dead_letter",
    )


def test_on_failure_is_entity_agnostic_and_logs_then_dispatches(mocker):
    """Regression: on_failure must log the failure and dispatch the DLQ payload
    without opening a DB session or writing any domain entity's status.

    Since the DummyImage decommission (doc 29 §3), on_failure no longer touches
    the database at all — entity FAILED transitions are owned by each task body,
    and stuck IN_PROCESS rows are handled by the stuck-job watchdog (doc 30).
    """
    mock_log = MagicMock()
    mocker.patch("src.worker.base_task.get_logger", return_value=mock_log)
    mock_dlq = mocker.patch("src.worker.tasks.dlq_dump")

    task = DiffpypeTask()
    task.name = "src.worker.tasks.run_ingest_batch"
    task.on_failure(RuntimeError("boom"), "task-1", (42,), {"batch_id": 42}, None)

    # Failure is logged with the task args, and the payload reaches the DLQ.
    mock_log.error.assert_any_call(
        "task_failed",
        task_id="task-1",
        args=(42,),
        error="boom",
        exc_info=None,
    )
    mock_dlq.apply_async.assert_called_once()
    # No SessionLocal is even referenced by base_task anymore.
    import src.worker.base_task as base_task_module

    assert not hasattr(base_task_module, "SessionLocal")


def test_on_failure_dispatch_error_is_swallowed(mocker):
    """A DLQ dispatch failure must not raise out of on_failure."""
    mock_log = MagicMock()
    mocker.patch("src.worker.base_task.get_logger", return_value=mock_log)
    mock_dlq = mocker.patch("src.worker.tasks.dlq_dump")
    mock_dlq.apply_async.side_effect = RuntimeError("broker down")

    task = DiffpypeTask()
    task.name = "src.worker.tasks.some_task"
    # Must not raise.
    task.on_failure(ValueError("x"), "task-9", (), {}, None)

    mock_log.error.assert_any_call(
        "on_failure_dlq_dispatch_failed", task_id="task-9", exc_info=True
    )


def test_on_failure_handles_empty_args(mocker):
    """Empty task args must not crash on_failure; the DLQ payload still dispatches."""
    mock_dlq = mocker.patch("src.worker.tasks.dlq_dump")

    task = DiffpypeTask()
    task.name = "src.worker.tasks.some_task"
    task.on_failure(ValueError("x"), "task-0", (), {}, None)

    mock_dlq.apply_async.assert_called_once()


# ---------------------------------------------------------------------------
# TimeLimitedTask / DiffpypeTask contract enforcement
# ---------------------------------------------------------------------------


def test_time_limited_task_requires_soft_time_limit_seconds():
    with pytest.raises(TypeError, match="must declare its own soft_time_limit_seconds"):

        class _Missing(TimeLimitedTask):
            pass


def test_time_limited_task_abstract_base_is_exempt():
    """An abstract=True intermediate base doesn't need to satisfy its own contract."""

    class _AbstractBase(TimeLimitedTask):
        abstract = True

    assert _AbstractBase.abstract is True


def test_diffpype_task_requires_tracked_entity_model():
    with pytest.raises(TypeError, match="must declare tracked_entity_model"):

        class _Missing(DiffpypeTask):
            soft_time_limit_seconds = 60


def test_diffpype_task_rejects_wrong_sibling_inheritance():
    """Regression: a task accidentally subclassing another concrete task instead
    of DiffpypeTask directly must not silently inherit its declared values."""

    class _Real(DiffpypeTask):
        tracked_entity_model = NOT_TRACKED
        soft_time_limit_seconds = 100

    with pytest.raises(TypeError, match="must declare its own soft_time_limit_seconds"):

        class _Accidental(_Real):
            pass


def test_soft_time_limit_and_time_limit_properties_bridge_correctly():
    class _Real(DiffpypeTask):
        tracked_entity_model = NOT_TRACKED
        soft_time_limit_seconds = 100

    task = _Real()
    assert task.soft_time_limit == 100
    assert task.time_limit == 130  # soft + HARD_LIMIT_BUFFER_SECONDS (30)


# ---------------------------------------------------------------------------
# begin_tracked_job
# ---------------------------------------------------------------------------


class _FakeTrackedModel:
    __name__ = "_FakeTrackedModel"


class _TrackedTask(DiffpypeTask):
    tracked_entity_model = _FakeTrackedModel
    soft_time_limit_seconds = 100


class _UntrackedTask(DiffpypeTask):
    tracked_entity_model = NOT_TRACKED
    soft_time_limit_seconds = 100


def test_begin_tracked_job_transitions_pending_entity_to_in_process(mocker):
    entity = MagicMock(status=JobStatus.PENDING)
    db = MagicMock()
    db.get.return_value = entity

    result = _TrackedTask().begin_tracked_job(db, 1)

    assert result is entity
    assert entity.status == JobStatus.IN_PROCESS
    db.commit.assert_called_once()


def test_begin_tracked_job_skips_already_complete_entity(mocker):
    entity = MagicMock(status=JobStatus.COMPLETE)
    db = MagicMock()
    db.get.return_value = entity
    mock_log = MagicMock()
    mocker.patch("src.worker.base_task.get_logger", return_value=mock_log)

    result = _TrackedTask().begin_tracked_job(db, 1)

    assert result is None
    db.commit.assert_not_called()
    mock_log.warning.assert_called_once_with(
        "tracked_job_stale_redelivery_skipped",
        entity="_FakeTrackedModel",
        id=1,
        status="complete",
    )


def test_begin_tracked_job_skips_already_failed_entity():
    entity = MagicMock(status=JobStatus.FAILED)
    db = MagicMock()
    db.get.return_value = entity

    result = _TrackedTask().begin_tracked_job(db, 1)

    assert result is None
    db.commit.assert_not_called()


def test_begin_tracked_job_raises_for_not_tracked_task():
    with pytest.raises(TypeError, match="declared NOT_TRACKED"):
        _UntrackedTask().begin_tracked_job(MagicMock(), 1)


def test_begin_tracked_job_raises_assertion_for_missing_entity():
    db = MagicMock()
    db.get.return_value = None

    with pytest.raises(AssertionError, match="_FakeTrackedModel 99 not found"):
        _TrackedTask().begin_tracked_job(db, 99)


def test_not_tracked_repr():
    assert repr(NOT_TRACKED) == "NOT_TRACKED"
