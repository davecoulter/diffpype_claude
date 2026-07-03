from unittest.mock import MagicMock

import pytest

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

    sleep_and_update_status(42, 3, correlation_id="cid-1")

    mock_sleep.assert_called_once_with(3)
    mock_session.get.assert_called_once_with(DummyImage, 42)
    assert fake_image.status == JobStatus.COMPLETE
    mock_session.commit.assert_called_once()
    mock_session.close.assert_called_once()


def test_sleep_and_update_status_uses_default_sleep_duration(mocker):
    mock_sleep = mocker.patch("src.worker.tasks.time.sleep")
    _make_session(mocker)

    sleep_and_update_status(1)

    mock_sleep.assert_called_once_with(5)


def test_sleep_and_update_status_propagates_exception_and_closes_session(mocker):
    """The task body no longer swallows exceptions; they bubble to Celery/on_failure."""
    mocker.patch("src.worker.tasks.time.sleep")
    mock_session = _make_session(mocker)
    mock_session.commit.side_effect = RuntimeError("commit failed")

    with pytest.raises(RuntimeError, match="commit failed"):
        sleep_and_update_status(7, 2)

    mock_session.close.assert_called_once()
