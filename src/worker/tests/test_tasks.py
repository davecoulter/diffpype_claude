import pytest
from unittest.mock import MagicMock

from src.db.enums import JobStatus
from src.db.models import DummyImage
from src.worker.tasks import sleep_and_update_status


def _make_session(mocker, fake_image=None):
    mock_session = MagicMock()
    mock_session.get.return_value = fake_image or MagicMock(status=JobStatus.IN_PROCESS)
    mocker.patch("src.worker.tasks.SessionLocal", return_value=mock_session)
    return mock_session


def test_sleep_and_update_status_marks_image_complete(mocker):
    mock_sleep = mocker.patch("src.worker.tasks.time.sleep")
    fake_image = MagicMock(status=JobStatus.IN_PROCESS)
    mock_session = _make_session(mocker, fake_image)

    sleep_and_update_status(42, 3)

    mock_sleep.assert_called_once_with(3)
    mock_session.get.assert_called_once_with(DummyImage, 42)
    assert fake_image.status == JobStatus.COMPLETE
    mock_session.commit.assert_called_once()
    mock_session.close.assert_called_once()


def test_sleep_and_update_status_uses_default_sleep_duration(mocker):
    mock_sleep = mocker.patch("src.worker.tasks.time.sleep")
    mock_session = _make_session(mocker)

    sleep_and_update_status(1)

    mock_sleep.assert_called_once_with(5)


def test_sleep_and_update_status_writes_failed_on_exception(mocker):
    mocker.patch("src.worker.tasks.time.sleep", side_effect=RuntimeError("boom"))
    fake_image = MagicMock(status=JobStatus.IN_PROCESS)
    mock_session = _make_session(mocker, fake_image)

    with pytest.raises(RuntimeError, match="boom"):
        sleep_and_update_status(7, 2)

    mock_session.rollback.assert_called_once()
    assert fake_image.status == JobStatus.FAILED
    mock_session.commit.assert_called_once()
    mock_session.close.assert_called_once()


def test_sleep_and_update_status_reraises_after_failed_write(mocker):
    """If the failure-write itself errors, the original exception is still re-raised."""
    mocker.patch("src.worker.tasks.time.sleep", side_effect=ValueError("task error"))
    mock_session = MagicMock()
    mock_session.get.side_effect = [Exception("DB gone")]
    mocker.patch("src.worker.tasks.SessionLocal", return_value=mock_session)

    with pytest.raises(ValueError, match="task error"):
        sleep_and_update_status(9, 1)

    mock_session.close.assert_called_once()
