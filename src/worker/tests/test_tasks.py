import subprocess
from unittest.mock import MagicMock

import pytest

from src.db.enums import JobStatus
from src.db.models import DummyImage, JobConfiguration
from src.worker.tasks import dlq_dump, execute_cli_tool, sleep_and_update_status


def test_dlq_dump_logs_failed_task_payload(mocker):
    """dlq_dump must emit a structured warning with the full failure context."""
    mock_logger = MagicMock()
    mocker.patch("src.worker.tasks.get_logger", return_value=mock_logger)

    dlq_dump("src.worker.tasks.some_task", {"image_id": 42}, "Connection refused")

    mock_logger.warning.assert_called_once_with(
        "task_dead_lettered",
        failed_task_name="src.worker.tasks.some_task",
        task_kwargs={"image_id": 42},
        error_msg="Connection refused",
    )


def _make_session(mocker, fake_image=None):
    mock_session = MagicMock()
    mock_session.get.return_value = fake_image or MagicMock(status=JobStatus.IN_PROCESS)
    mocker.patch("src.worker.tasks.SessionLocal", return_value=mock_session)
    return mock_session


def test_sleep_and_update_status_marks_image_complete_and_stamps_times(mocker):
    mock_sleep = mocker.patch("src.worker.tasks.time.sleep")
    mocker.patch("src.worker.tasks.func.now", return_value="NOW")
    fake_image = MagicMock(status=JobStatus.IN_PROCESS)
    mock_session = _make_session(mocker, fake_image)

    sleep_and_update_status(42, 3)

    mock_sleep.assert_called_once_with(3)
    assert mock_session.get.call_count == 2
    mock_session.get.assert_called_with(DummyImage, 42)
    assert fake_image.status == JobStatus.COMPLETE
    assert fake_image.job_started_at == "NOW"
    assert fake_image.job_finished_at == "NOW"
    # Two short transactions: the start-time write, then the completion write.
    assert mock_session.commit.call_count == 2
    assert mock_session.close.call_count == 2


def test_sleep_and_update_status_records_start_before_sleeping(mocker):
    """job_started_at must be committed before the sleep so a mid-run crash is recoverable."""
    order = []
    mocker.patch("src.worker.tasks.time.sleep", side_effect=lambda *_: order.append("sleep"))
    mocker.patch("src.worker.tasks.func.now", return_value="NOW")
    mock_session = _make_session(mocker)
    mock_session.commit.side_effect = lambda: order.append("commit")

    sleep_and_update_status(1, 1)

    assert order[0] == "commit"
    assert order.index("commit") < order.index("sleep")


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


# ---------------------------------------------------------------------------
# execute_cli_tool
# ---------------------------------------------------------------------------


def _make_cli_session(mocker, job_kwargs=None):
    fake_config = MagicMock(spec=JobConfiguration, job_kwargs=job_kwargs or {"inim": "sci.fits"})
    mock_session = MagicMock()
    mock_session.get.return_value = fake_config
    mocker.patch("src.worker.tasks.SessionLocal", return_value=mock_session)
    return mock_session, fake_config


def test_execute_cli_tool_calls_subprocess_with_correct_list(mocker):
    mock_session, _ = _make_cli_session(mocker, {"inim": "sci.fits", "c": "t"})
    mock_run = mocker.patch("src.worker.tasks.subprocess.run", return_value=MagicMock(stdout=""))

    execute_cli_tool(1, "hotpants")

    mock_session.get.assert_called_once_with(JobConfiguration, 1)
    mock_run.assert_called_once_with(
        ["hotpants", "-inim", "sci.fits", "-c", "t"],
        capture_output=True,
        text=True,
        check=True,
    )


def test_execute_cli_tool_saves_execution_command(mocker):
    mock_session, fake_config = _make_cli_session(mocker, {"inim": "sci.fits"})
    mocker.patch("src.worker.tasks.subprocess.run", return_value=MagicMock(stdout=""))

    execute_cli_tool(2, "hotpants")

    assert fake_config.execution_command == "hotpants -inim sci.fits"
    mock_session.commit.assert_called_once()


def test_execute_cli_tool_closes_session_on_subprocess_error(mocker):
    mock_session, _ = _make_cli_session(mocker)
    mocker.patch(
        "src.worker.tasks.subprocess.run",
        side_effect=subprocess.CalledProcessError(1, "hotpants"),
    )

    with pytest.raises(subprocess.CalledProcessError):
        execute_cli_tool(3, "hotpants")

    mock_session.close.assert_called_once()


def test_execute_cli_tool_handles_none_job_kwargs(mocker):
    mock_session, _ = _make_cli_session(mocker, None)
    mock_session.get.return_value = MagicMock(spec=JobConfiguration, job_kwargs=None)
    mock_run = mocker.patch("src.worker.tasks.subprocess.run", return_value=MagicMock(stdout=""))

    execute_cli_tool(4, "mytool")

    mock_run.assert_called_once_with(["mytool"], capture_output=True, text=True, check=True)
