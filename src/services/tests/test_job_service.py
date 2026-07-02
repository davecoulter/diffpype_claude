from unittest.mock import MagicMock

from src.db.enums import JobStatus
from src.db.models import DummyImage
from src.services.job_service import dispatch_dummy_job


def test_dispatch_dummy_job_creates_image_commits_and_returns_ids(mocker):
    mock_db = MagicMock()

    def fake_refresh(obj):
        obj.id = 99

    mock_db.refresh.side_effect = fake_refresh

    fake_result = MagicMock(id="test-task-id")
    mock_delay = mocker.patch(
        "src.services.job_service.sleep_and_update_status.delay",
        return_value=fake_result,
    )

    job_id, image_id = dispatch_dummy_job(mock_db)

    assert job_id == "test-task-id"
    assert image_id == 99
    mock_db.add.assert_called_once()
    assert mock_db.commit.call_count == 2
    mock_delay.assert_called_once_with(99)


def test_dispatch_dummy_job_sets_in_process_status(mocker):
    mock_db = MagicMock()
    mock_db.refresh.side_effect = lambda obj: setattr(obj, "id", 1)
    mocker.patch(
        "src.services.job_service.sleep_and_update_status.delay",
        return_value=MagicMock(id="some-id"),
    )

    dispatch_dummy_job(mock_db)

    added_image = mock_db.add.call_args[0][0]
    assert isinstance(added_image, DummyImage)
    assert added_image.status == JobStatus.IN_PROCESS


def test_dispatch_dummy_job_stores_task_id_on_image(mocker):
    mock_db = MagicMock()
    mock_db.refresh.side_effect = lambda obj: setattr(obj, "id", 5)
    mocker.patch(
        "src.services.job_service.sleep_and_update_status.delay",
        return_value=MagicMock(id="stored-task-id"),
    )

    dispatch_dummy_job(mock_db)

    added_image = mock_db.add.call_args[0][0]
    assert added_image.latest_job_id == "stored-task-id"
