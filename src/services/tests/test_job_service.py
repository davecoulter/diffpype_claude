import datetime as dt
from types import SimpleNamespace
from unittest.mock import MagicMock

from src.db.enums import JobStatus
from src.services.job_service import create_job_configuration, reconcile_stuck_jobs


def _execute_result(rows):
    result = MagicMock()
    result.scalars.return_value.all.return_value = rows
    return result


def test_create_job_configuration_flushes_and_returns_row():
    db = MagicMock()

    jc = create_job_configuration(
        db,
        user_id=1,
        task_name="src.worker.tasks.run_ingest_batch",
        job_kwargs={"a": 1},
    )

    db.add.assert_called_once_with(jc)
    db.flush.assert_called_once()
    assert jc.user_id == 1
    assert jc.task_name == "src.worker.tasks.run_ingest_batch"
    assert jc.job_kwargs == {"a": 1}


def test_reconcile_marks_only_stale_in_process_jobs_failed():
    now = dt.datetime.now(dt.timezone.utc)
    stale = SimpleNamespace(
        id=1,
        status=JobStatus.IN_PROCESS,
        updated_at=now - dt.timedelta(seconds=7200),
        job_configuration=None,
    )
    fresh = SimpleNamespace(
        id=2,
        status=JobStatus.IN_PROCESS,
        updated_at=now - dt.timedelta(seconds=10),
        job_configuration=None,
    )
    db = MagicMock()
    # First query -> IngestBatch rows; second -> Level3Mosaic rows (none).
    db.execute.side_effect = [_execute_result([stale, fresh]), _execute_result([])]

    result = reconcile_stuck_jobs(db, staleness_timeout_seconds=3600)

    db.rollback.assert_called_once()
    db.commit.assert_called_once()
    assert stale.status == JobStatus.FAILED
    assert fresh.status == JobStatus.IN_PROCESS
    assert result == [
        {"entity": "IngestBatch", "id": 1, "age_seconds": result[0]["age_seconds"]}
    ]
    assert result[0]["age_seconds"] > 3600


def test_reconcile_honors_per_job_staleness_override():
    now = dt.datetime.now(dt.timezone.utc)
    # Aged 200s: under the global 3600 default (would survive), but a per-job
    # override of 100s makes it stale.
    job_config = SimpleNamespace(job_kwargs={"staleness_timeout_seconds": 100})
    row = SimpleNamespace(
        id=5,
        status=JobStatus.IN_PROCESS,
        updated_at=now - dt.timedelta(seconds=200),
        job_configuration=job_config,
    )
    db = MagicMock()
    db.execute.side_effect = [_execute_result([row]), _execute_result([])]

    result = reconcile_stuck_jobs(db, staleness_timeout_seconds=3600)

    assert row.status == JobStatus.FAILED
    assert len(result) == 1


def test_reconcile_no_stale_jobs_returns_empty_but_still_commits():
    db = MagicMock()
    db.execute.side_effect = [_execute_result([]), _execute_result([])]

    result = reconcile_stuck_jobs(db)

    assert result == []
    db.rollback.assert_called_once()
    db.commit.assert_called_once()
