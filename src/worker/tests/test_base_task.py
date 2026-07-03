from unittest.mock import MagicMock

from src.db.enums import JobStatus
from src.db.models import DummyImage
from src.worker.base_task import DiffpypeTask


def test_on_failure_rolls_back_and_marks_failed(mocker):
    fake_image = MagicMock(status=JobStatus.IN_PROCESS)
    mock_session = MagicMock()
    mock_session.get.return_value = fake_image
    mocker.patch("src.worker.base_task.SessionLocal", return_value=mock_session)

    task = DiffpypeTask()
    task.on_failure(
        RuntimeError("boom"),
        "task-123",
        (7, 2),
        {"correlation_id": "cid-abc"},
        None,
    )

    mock_session.rollback.assert_called_once()
    mock_session.get.assert_called_once_with(DummyImage, 7)
    assert fake_image.status == JobStatus.FAILED
    mock_session.commit.assert_called_once()
    mock_session.close.assert_called_once()


def test_on_failure_handles_missing_image(mocker):
    mock_session = MagicMock()
    mock_session.get.return_value = None
    mocker.patch("src.worker.base_task.SessionLocal", return_value=mock_session)

    task = DiffpypeTask()
    task.on_failure(ValueError("x"), "task-9", (999,), {}, None)

    mock_session.rollback.assert_called_once()
    mock_session.commit.assert_not_called()
    mock_session.close.assert_called_once()


def test_on_failure_handles_empty_args(mocker):
    mock_session = MagicMock()
    mock_session.get.return_value = None
    mocker.patch("src.worker.base_task.SessionLocal", return_value=mock_session)

    task = DiffpypeTask()
    task.on_failure(ValueError("x"), "task-0", (), {}, None)

    mock_session.get.assert_called_once_with(DummyImage, None)
    mock_session.close.assert_called_once()
