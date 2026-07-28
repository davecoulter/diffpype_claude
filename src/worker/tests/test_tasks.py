import subprocess
from unittest.mock import MagicMock

import pandas as pd
import pytest

from src.db.enums import JobStatus
from src.db.models import DummyImage, IngestBatch, JobConfiguration, Level3Mosaic
from src.worker.tasks import (
    dlq_dump,
    execute_cli_tool,
    run_ingest_batch,
    run_mosaic_drizzle,
    sleep_and_update_status,
)


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
    mocker.patch(
        "src.worker.tasks.time.sleep", side_effect=lambda *_: order.append("sleep")
    )
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
    fake_config = MagicMock(
        spec=JobConfiguration, job_kwargs=job_kwargs or {"inim": "sci.fits"}
    )
    mock_session = MagicMock()
    mock_session.get.return_value = fake_config
    mocker.patch("src.worker.tasks.SessionLocal", return_value=mock_session)
    return mock_session, fake_config


def test_execute_cli_tool_calls_subprocess_with_correct_list(mocker):
    mock_session, _ = _make_cli_session(mocker, {"inim": "sci.fits", "c": "t"})
    mock_run = mocker.patch(
        "src.worker.tasks.subprocess.run", return_value=MagicMock(stdout="")
    )

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


# ---------------------------------------------------------------------------
# run_ingest_batch
# ---------------------------------------------------------------------------


def _make_ingest_session(mocker, fake_batch=None):
    batch = fake_batch or MagicMock(
        spec=IngestBatch, id=1, project_id=1, s3_prefix="raw/"
    )
    mock_session = MagicMock()
    mock_session.get.return_value = batch
    mocker.patch("src.worker.tasks.SessionLocal", return_value=mock_session)
    # download_file is mocked in these tests (writes nothing real to disk), so
    # os.remove has nothing real to delete unless a test overrides this itself.
    mocker.patch("src.worker.tasks.os.remove")
    return mock_session, batch


def test_run_ingest_batch_transitions_pending_to_complete(mocker):
    mock_session, batch = _make_ingest_session(mocker)
    fake_storage = MagicMock()
    fake_storage.list_prefix.return_value = ["raw/a.fits", "raw/b.fits"]
    mocker.patch("src.worker.tasks.get_storage_service", return_value=fake_storage)
    mocker.patch(
        "src.worker.tasks.ingest_service.parse_fits_headers",
        side_effect=lambda paths: pd.DataFrame([{"base_filename": paths[0]}]),
    )
    mock_upsert = mocker.patch(
        "src.worker.tasks.ingest_service.bulk_upsert_images_and_calibrations"
    )

    run_ingest_batch(1)

    assert batch.status == JobStatus.COMPLETE
    assert batch.total_files == 2
    assert batch.processed_files == 2
    mock_upsert.assert_called_once()
    upserted_df = mock_upsert.call_args[0][2]
    assert len(upserted_df) == 2  # both files' parsed rows concatenated
    assert mock_session.close.call_count == 1


def test_run_ingest_batch_downloads_each_listed_key(mocker):
    mock_session, batch = _make_ingest_session(mocker)
    fake_storage = MagicMock()
    fake_storage.list_prefix.return_value = ["raw/a.fits"]
    mocker.patch("src.worker.tasks.get_storage_service", return_value=fake_storage)
    mocker.patch(
        "src.worker.tasks.ingest_service.parse_fits_headers",
        return_value=pd.DataFrame(),
    )
    mocker.patch("src.worker.tasks.ingest_service.bulk_upsert_images_and_calibrations")

    run_ingest_batch(1)

    fake_storage.download_file.assert_called_once()
    assert fake_storage.download_file.call_args[0][0] == "raw/a.fits"


def test_run_ingest_batch_parses_one_file_at_a_time(mocker):
    """parse_fits_headers is called per-file (a single-element list each time), not
    once for the whole batch — this is what keeps peak memory/disk to ~one file."""
    mock_session, batch = _make_ingest_session(mocker)
    fake_storage = MagicMock()
    fake_storage.list_prefix.return_value = ["raw/a.fits", "raw/b.fits", "raw/c.fits"]
    mocker.patch("src.worker.tasks.get_storage_service", return_value=fake_storage)
    mock_parse = mocker.patch(
        "src.worker.tasks.ingest_service.parse_fits_headers",
        return_value=pd.DataFrame(),
    )
    mocker.patch("src.worker.tasks.ingest_service.bulk_upsert_images_and_calibrations")

    run_ingest_batch(1)

    assert mock_parse.call_count == 3
    for call in mock_parse.call_args_list:
        assert len(call.args[0]) == 1  # always a single-element path list


def test_run_ingest_batch_increments_processed_files_progressively(mocker):
    mock_session, batch = _make_ingest_session(mocker)
    fake_storage = MagicMock()
    fake_storage.list_prefix.return_value = ["raw/a.fits", "raw/b.fits"]
    mocker.patch("src.worker.tasks.get_storage_service", return_value=fake_storage)
    mocker.patch(
        "src.worker.tasks.ingest_service.parse_fits_headers",
        return_value=pd.DataFrame(),
    )
    mocker.patch("src.worker.tasks.ingest_service.bulk_upsert_images_and_calibrations")

    observed_progress = []
    mock_session.commit.side_effect = lambda: observed_progress.append(
        batch.processed_files
    )

    run_ingest_batch(1)

    # processed_files must have visibly been 1, then 2, before the task finished —
    # not just jump straight from 0 to 2 at the very end.
    assert 1 in observed_progress
    assert 2 in observed_progress


def test_run_ingest_batch_logs_progress_per_file(mocker):
    mock_session, batch = _make_ingest_session(mocker)
    fake_storage = MagicMock()
    fake_storage.list_prefix.return_value = ["raw/a.fits", "raw/b.fits"]
    mocker.patch("src.worker.tasks.get_storage_service", return_value=fake_storage)
    mocker.patch(
        "src.worker.tasks.ingest_service.parse_fits_headers",
        return_value=pd.DataFrame(),
    )
    mocker.patch("src.worker.tasks.ingest_service.bulk_upsert_images_and_calibrations")
    mock_logger = MagicMock()
    mocker.patch("src.worker.tasks.get_logger", return_value=mock_logger)

    run_ingest_batch(1)

    progress_calls = [
        c
        for c in mock_logger.info.call_args_list
        if c.args[0] == "ingest_file_processed"
    ]
    assert len(progress_calls) == 2
    assert progress_calls[0].kwargs["index"] == 1
    assert progress_calls[1].kwargs["index"] == 2
    assert progress_calls[1].kwargs["total"] == 2


def test_run_ingest_batch_removes_temp_file_after_each_file(mocker):
    """Confirms the streaming shape: each file is deleted right after parsing,
    not left on disk until the whole batch finishes."""
    mock_session, batch = _make_ingest_session(mocker)
    fake_storage = MagicMock()
    fake_storage.list_prefix.return_value = ["raw/a.fits"]
    mocker.patch("src.worker.tasks.get_storage_service", return_value=fake_storage)
    mocker.patch(
        "src.worker.tasks.ingest_service.parse_fits_headers",
        return_value=pd.DataFrame(),
    )
    mocker.patch("src.worker.tasks.ingest_service.bulk_upsert_images_and_calibrations")
    mock_remove = mocker.patch("src.worker.tasks.os.remove")

    run_ingest_batch(1)

    mock_remove.assert_called_once()
    assert mock_remove.call_args[0][0].endswith("a.fits")


def test_run_ingest_batch_handles_zero_files_without_crashing(mocker):
    mock_session, batch = _make_ingest_session(mocker)
    fake_storage = MagicMock()
    fake_storage.list_prefix.return_value = []
    mocker.patch("src.worker.tasks.get_storage_service", return_value=fake_storage)
    mock_parse = mocker.patch("src.worker.tasks.ingest_service.parse_fits_headers")
    mock_upsert = mocker.patch(
        "src.worker.tasks.ingest_service.bulk_upsert_images_and_calibrations"
    )

    run_ingest_batch(1)

    mock_parse.assert_not_called()
    mock_upsert.assert_called_once()
    empty_df = mock_upsert.call_args[0][2]
    assert empty_df.empty
    assert batch.status == JobStatus.COMPLETE
    assert batch.processed_files == 0


def test_run_ingest_batch_marks_failed_and_reraises_on_error(mocker):
    mock_session, batch = _make_ingest_session(mocker)
    mocker.patch(
        "src.worker.tasks.get_storage_service",
        side_effect=RuntimeError("storage unreachable"),
    )

    with pytest.raises(RuntimeError, match="storage unreachable"):
        run_ingest_batch(1)

    assert batch.status == JobStatus.FAILED
    mock_session.rollback.assert_called_once()
    mock_session.close.assert_called_once()


def test_run_ingest_batch_missing_batch_raises_assertion(mocker):
    mock_session = MagicMock()
    mock_session.get.return_value = None
    mocker.patch("src.worker.tasks.SessionLocal", return_value=mock_session)

    with pytest.raises(AssertionError, match="IngestBatch 99 not found"):
        run_ingest_batch(99)

    mock_session.close.assert_called_once()


# ---------------------------------------------------------------------------
# run_mosaic_drizzle
# ---------------------------------------------------------------------------


def _make_mosaic_session(mocker, fake_mosaic=None):
    mosaic = fake_mosaic or MagicMock(spec=Level3Mosaic, id=1)
    mock_session = MagicMock()
    mock_session.get.return_value = mosaic
    mocker.patch("src.worker.tasks.SessionLocal", return_value=mock_session)
    return mock_session, mosaic


def test_run_mosaic_drizzle_transitions_pending_to_complete(mocker):
    mock_session, mosaic = _make_mosaic_session(mocker)
    mocker.patch("src.worker.tasks.time.sleep")

    run_mosaic_drizzle(1)

    assert mosaic.status == JobStatus.COMPLETE
    assert mock_session.close.call_count == 1


def test_run_mosaic_drizzle_marks_failed_and_reraises_on_error(mocker):
    mock_session, mosaic = _make_mosaic_session(mocker)
    mocker.patch(
        "src.worker.tasks.time.sleep", side_effect=RuntimeError("drizzle boom")
    )

    with pytest.raises(RuntimeError, match="drizzle boom"):
        run_mosaic_drizzle(1)

    assert mosaic.status == JobStatus.FAILED
    mock_session.rollback.assert_called_once()
    mock_session.close.assert_called_once()


def test_run_mosaic_drizzle_missing_mosaic_raises_assertion(mocker):
    mock_session = MagicMock()
    mock_session.get.return_value = None
    mocker.patch("src.worker.tasks.SessionLocal", return_value=mock_session)

    with pytest.raises(AssertionError, match="Level3Mosaic 99 not found"):
        run_mosaic_drizzle(99)

    mock_session.close.assert_called_once()


def test_execute_cli_tool_handles_none_job_kwargs(mocker):
    mock_session, _ = _make_cli_session(mocker, None)
    mock_session.get.return_value = MagicMock(spec=JobConfiguration, job_kwargs=None)
    mock_run = mocker.patch(
        "src.worker.tasks.subprocess.run", return_value=MagicMock(stdout="")
    )

    execute_cli_tool(4, "mytool")

    mock_run.assert_called_once_with(
        ["mytool"], capture_output=True, text=True, check=True
    )
