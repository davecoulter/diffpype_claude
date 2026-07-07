from unittest.mock import MagicMock

from structlog.contextvars import bind_contextvars

from src.db.enums import JobStatus
from src.db.models import DummyImage
from src.services.job_service import dispatch_dummy_job, get_dummy_job

CONFIG = {"sleep_duration": 5}


def test_get_dummy_job_returns_image_for_known_id():
    fake_image = MagicMock(spec=DummyImage)
    mock_db = MagicMock()
    mock_db.get.return_value = fake_image

    result = get_dummy_job(mock_db, 5)

    mock_db.get.assert_called_once_with(DummyImage, 5)
    assert result is fake_image


def test_get_dummy_job_returns_none_for_unknown_id():
    mock_db = MagicMock()
    mock_db.get.return_value = None

    result = get_dummy_job(mock_db, 999)

    assert result is None


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

    job_id, image_id = dispatch_dummy_job(mock_db, CONFIG)

    assert job_id == "test-task-id"
    assert image_id == 99
    mock_db.add.assert_called_once()
    assert mock_db.commit.call_count == 2
    mock_delay.assert_called_once_with(99, 5, correlation_id=None)


def test_dispatch_dummy_job_sets_in_process_status(mocker):
    mock_db = MagicMock()
    mock_db.refresh.side_effect = lambda obj: setattr(obj, "id", 1)
    mocker.patch(
        "src.services.job_service.sleep_and_update_status.delay",
        return_value=MagicMock(id="some-id"),
    )

    dispatch_dummy_job(mock_db, CONFIG)

    added_image = mock_db.add.call_args[0][0]
    assert isinstance(added_image, DummyImage)
    assert added_image.status == JobStatus.IN_PROCESS


def test_dispatch_dummy_job_stores_config_in_job_configuration(mocker):
    mock_db = MagicMock()
    mock_db.refresh.side_effect = lambda obj: setattr(obj, "id", 2)
    mocker.patch(
        "src.services.job_service.sleep_and_update_status.delay",
        return_value=MagicMock(id="x"),
    )

    dispatch_dummy_job(mock_db, CONFIG)

    added_image = mock_db.add.call_args[0][0]
    assert added_image.job_configuration.job_kwargs == CONFIG


def test_dispatch_dummy_job_records_execution_command(mocker):
    mock_db = MagicMock()
    mock_db.refresh.side_effect = lambda obj: setattr(obj, "id", 3)
    mocker.patch(
        "src.services.job_service.sleep_and_update_status.delay",
        return_value=MagicMock(id="x"),
    )

    dispatch_dummy_job(mock_db, {"sleep_duration": 8})

    added_image = mock_db.add.call_args[0][0]
    assert added_image.job_configuration.execution_command == (
        "diffpype-manage run-dummy --sleep 8"
    )


def test_dispatch_dummy_job_stores_task_id_on_image(mocker):
    mock_db = MagicMock()
    mock_db.refresh.side_effect = lambda obj: setattr(obj, "id", 5)
    mocker.patch(
        "src.services.job_service.sleep_and_update_status.delay",
        return_value=MagicMock(id="stored-task-id"),
    )

    dispatch_dummy_job(mock_db, CONFIG)

    added_image = mock_db.add.call_args[0][0]
    assert added_image.latest_job_id == "stored-task-id"


def test_dispatch_dummy_job_passes_sleep_duration_to_task(mocker):
    mock_db = MagicMock()
    mock_db.refresh.side_effect = lambda obj: setattr(obj, "id", 7)
    mock_delay = mocker.patch(
        "src.services.job_service.sleep_and_update_status.delay",
        return_value=MagicMock(id="y"),
    )

    dispatch_dummy_job(mock_db, {"sleep_duration": 3})

    mock_delay.assert_called_once_with(7, 3, correlation_id=None)


def test_dispatch_dummy_job_forwards_bound_correlation_id(mocker):
    mock_db = MagicMock()
    mock_db.refresh.side_effect = lambda obj: setattr(obj, "id", 8)
    mock_delay = mocker.patch(
        "src.services.job_service.sleep_and_update_status.delay",
        return_value=MagicMock(id="z"),
    )
    bind_contextvars(correlation_id="cid-xyz")

    dispatch_dummy_job(mock_db, CONFIG)

    mock_delay.assert_called_once_with(8, 5, correlation_id="cid-xyz")
