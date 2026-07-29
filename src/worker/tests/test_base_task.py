from unittest.mock import MagicMock

from sqlalchemy.exc import OperationalError as SAOperationalError

from src.core.config import settings
from src.worker.base_task import DiffpypeTask


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
