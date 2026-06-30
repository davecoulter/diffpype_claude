from unittest.mock import MagicMock

from src.db.models import DummyImage
from src.worker.tasks import sleep_and_update_status


def test_sleep_and_update_status_marks_image_success(mocker):
    mocker.patch("src.worker.tasks.time.sleep")

    fake_image = MagicMock(status="Running")
    mock_session = MagicMock()
    mock_session.get.return_value = fake_image
    mocker.patch("src.worker.tasks.SessionLocal", return_value=mock_session)

    sleep_and_update_status(42)

    mock_session.get.assert_called_once_with(DummyImage, 42)
    assert fake_image.status == "Success"
    mock_session.commit.assert_called_once()
    mock_session.close.assert_called_once()
