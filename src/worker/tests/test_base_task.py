from unittest.mock import MagicMock

from sqlalchemy.exc import OperationalError as SAOperationalError

from src.core.config import settings
from src.db.enums import JobStatus
from src.db.models import DummyImage
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


def test_on_failure_dispatches_dlq_even_when_db_is_down(mocker):
    """DLQ dispatch must fire even if the DB status update itself fails."""
    mock_session = MagicMock()
    mock_session.get.side_effect = SAOperationalError("db down", None, None)
    mocker.patch("src.worker.base_task.SessionLocal", return_value=mock_session)
    mock_dlq = mocker.patch("src.worker.tasks.dlq_dump")

    task = DiffpypeTask()
    task.name = "src.worker.tasks.some_task"
    task.on_failure(SAOperationalError("db down", None, None), "task-1", (7,), {}, None)

    mock_dlq.apply_async.assert_called_once()
    call_kwargs = mock_dlq.apply_async.call_args
    assert call_kwargs.kwargs["queue"] == "dead_letter"


def test_retry_limits_match_settings():
    assert DiffpypeTask.max_retries == settings.celery_task_max_retries
    assert DiffpypeTask.default_retry_delay == settings.celery_task_retry_delay


def test_on_failure_dispatches_to_dlq(mocker):
    """Permanently failed tasks must be routed to the dead_letter queue."""
    mock_session = MagicMock()
    mock_session.get.return_value = None
    mocker.patch("src.worker.base_task.SessionLocal", return_value=mock_session)
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


def test_on_failure_rolls_back_and_marks_failed(mocker):
    mocker.patch("src.worker.base_task.func.now", return_value="NOW")
    mocker.patch("src.worker.tasks.dlq_dump")
    fake_image = MagicMock(status=JobStatus.IN_PROCESS)
    mock_session = MagicMock()
    mock_session.get.return_value = fake_image
    mocker.patch("src.worker.base_task.SessionLocal", return_value=mock_session)

    task = DiffpypeTask()
    task.on_failure(RuntimeError("boom"), "task-123", (7, 2), {}, None)

    mock_session.rollback.assert_called_once()
    mock_session.get.assert_called_once_with(DummyImage, 7)
    assert fake_image.status == JobStatus.FAILED
    assert fake_image.job_finished_at == "NOW"
    mock_session.commit.assert_called_once()
    mock_session.close.assert_called_once()


def test_on_failure_handles_missing_image(mocker):
    mocker.patch("src.worker.tasks.dlq_dump")
    mock_session = MagicMock()
    mock_session.get.return_value = None
    mocker.patch("src.worker.base_task.SessionLocal", return_value=mock_session)

    task = DiffpypeTask()
    task.on_failure(ValueError("x"), "task-9", (999,), {}, None)

    mock_session.rollback.assert_called_once()
    mock_session.commit.assert_not_called()
    mock_session.close.assert_called_once()


def test_on_failure_handles_empty_args(mocker):
    mocker.patch("src.worker.tasks.dlq_dump")
    mock_session = MagicMock()
    mock_session.get.return_value = None
    mocker.patch("src.worker.base_task.SessionLocal", return_value=mock_session)

    task = DiffpypeTask()
    task.on_failure(ValueError("x"), "task-0", (), {}, None)

    mock_session.get.assert_called_once_with(DummyImage, None)
    mock_session.close.assert_called_once()
