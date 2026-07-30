import os
import subprocess
import tempfile
import time

import pandas as pd

from src.core.config import settings
from src.core.logger import get_logger
from src.db.enums import JobStatus
from src.db.models import IngestBatch, JobConfiguration, Level3Mosaic
from src.db.session import SessionLocal
from src.services import ingest_service, job_service, storage_service
from src.services.storage_service import get_storage_service
from src.worker.base_task import NOT_TRACKED, DiffpypeTask, TimeLimitedTask
from src.worker.celery_app import celery_app
from src.worker.utils import build_cli_command


class _IngestBatchTask(DiffpypeTask):
    tracked_entity_model = IngestBatch
    soft_time_limit_seconds = settings.ingest_batch_soft_time_limit_seconds


@celery_app.task(
    base=_IngestBatchTask, bind=True, name="src.worker.tasks.run_ingest_batch"
)
def run_ingest_batch(self, batch_id: int) -> None:
    """Scan an IngestBatch's storage prefix and bulk-upsert Level2Image/Level2Calibration rows.

    Uses ``begin_tracked_job`` (DiffpypeTask) for its IN_PROCESS transition:
    guarantees no orphaned IN_PROCESS row for the entity it actually tracks,
    and refuses to resume/overwrite a row the stuck-job watchdog already
    resolved — a stale redelivery arriving after the watchdog gave up (doc 30).
    """
    log = get_logger()
    log.info("ingest_batch_started", batch_id=batch_id)

    db = SessionLocal()
    try:
        batch = self.begin_tracked_job(db, batch_id)
        if batch is None:
            return

        storage = get_storage_service()
        keys = storage.list_prefix(batch.s3_prefix)
        batch.total_files = len(keys)
        batch.processed_files = 0
        db.commit()

        # One file on disk at a time, not all of them at once: downloading every
        # file into the temp dir up front (the previous shape) meant peak memory/
        # disk footprint scaled with total batch size, which OOM-killed the whole
        # container on a real ~20-file batch of real FITS data (WORKER_LIGHT_MEM_LIMIT
        # is 512m). Streaming download->parse->delete per file keeps peak footprint
        # to ~one file, and doubles as real per-file progress (processed_files,
        # ingest_file_processed) instead of a single all-or-nothing jump at the end.
        header_frames: list[pd.DataFrame] = []
        with tempfile.TemporaryDirectory() as tmp_dir:
            for index, key in enumerate(keys, start=1):
                local_path = os.path.join(tmp_dir, os.path.basename(key))
                storage.download_file(key, local_path)
                header_frames.append(ingest_service.parse_fits_headers([local_path]))
                os.remove(local_path)

                batch.processed_files = index
                db.commit()
                log.info(
                    "ingest_file_processed",
                    batch_id=batch_id,
                    key=key,
                    index=index,
                    total=len(keys),
                )

        header_df = (
            pd.concat(header_frames, ignore_index=True)
            if header_frames
            else pd.DataFrame()
        )
        ingest_service.bulk_upsert_images_and_calibrations(
            db, batch.project_id, header_df
        )

        batch.status = JobStatus.COMPLETE
        db.commit()
        log.info(
            "ingest_batch_completed", batch_id=batch_id, total_files=batch.total_files
        )
    except Exception as exc:
        log.error(
            "ingest_batch_failed", batch_id=batch_id, error=str(exc), exc_info=True
        )
        db.rollback()
        batch = db.get(IngestBatch, batch_id)
        if batch is not None:
            batch.status = JobStatus.FAILED
            db.commit()
        raise
    finally:
        db.close()


class _MosaicDrizzleTask(DiffpypeTask):
    tracked_entity_model = Level3Mosaic
    soft_time_limit_seconds = settings.mosaic_drizzle_soft_time_limit_seconds


@celery_app.task(
    base=_MosaicDrizzleTask, bind=True, name="src.worker.tasks.run_mosaic_drizzle"
)
def run_mosaic_drizzle(self, mosaic_id: int) -> None:
    """Placeholder drizzle execution: sleeps and transitions to COMPLETE.

    The Level3Mosaic row itself (footprint, barycenter, and its M2M-derived
    constituent calibrations) is already the complete job specification —
    only the actual pixel-level drizzle is deferred, to a future
    JWST-pipeline-specific doc. Uses ``begin_tracked_job`` for the same
    stale-redelivery protection as ``run_ingest_batch``.
    """
    log = get_logger()
    log.info("mosaic_drizzle_started", mosaic_id=mosaic_id)

    db = SessionLocal()
    try:
        mosaic = self.begin_tracked_job(db, mosaic_id)
        if mosaic is None:
            return

        time.sleep(5)

        mosaic.status = JobStatus.COMPLETE
        db.commit()
        log.info("mosaic_drizzle_completed", mosaic_id=mosaic_id)
    except Exception as exc:
        log.error(
            "mosaic_drizzle_failed", mosaic_id=mosaic_id, error=str(exc), exc_info=True
        )
        db.rollback()
        mosaic = db.get(Level3Mosaic, mosaic_id)
        if mosaic is not None:
            mosaic.status = JobStatus.FAILED
            db.commit()
        raise
    finally:
        db.close()


class _StagingSyncTask(DiffpypeTask):
    tracked_entity_model = NOT_TRACKED
    soft_time_limit_seconds = settings.staging_sync_soft_time_limit_seconds


@celery_app.task(base=_StagingSyncTask, name="src.worker.tasks.run_staging_sync")
def run_staging_sync(staging_location: str, canonical_prefix: str) -> None:
    """Mirror a staging location into the canonical bucket (streamed ``mc mirror``).

    Built on DiffpypeTask (unlike ``run_ingest_batch``): it owns no DB status
    entity (``tracked_entity_model = NOT_TRACKED``), so the base's
    entity-agnostic retry/DLQ behavior is exactly right — a transient failure
    retries, a permanent one dead-letters, and the underlying ``mc mirror`` is
    idempotent so a redelivered run is always safe. Bounds a hung ``mc``
    subprocess (network partition mid-transfer, not a clean crash) via
    ``_StagingSyncTask.soft_time_limit_seconds`` — ``sync_staging_to_canonical``
    catches ``SoftTimeLimitExceeded`` to kill the subprocess before re-raising.
    Not auto-retried on a timeout (``SoftTimeLimitExceeded`` isn't in
    ``DiffpypeTask.autoretry_for``): a hang that already exceeded a generous
    soft limit likely hangs again immediately, so it dead-letters for operator
    attention instead of retrying blindly.
    """
    storage_service.sync_staging_to_canonical(staging_location, canonical_prefix)


class _SyncStagingCronTask(DiffpypeTask):
    tracked_entity_model = NOT_TRACKED
    soft_time_limit_seconds = settings.staging_sync_soft_time_limit_seconds


@celery_app.task(base=_SyncStagingCronTask, name="src.worker.tasks.sync_staging_cron")
def sync_staging_cron() -> None:
    """Celery Beat entry point: mirror the configured staging location into the canonical bucket root."""
    storage_service.sync_staging_to_canonical(settings.staging_location, "")


class _ReconcileStuckJobsCronTask(DiffpypeTask):
    tracked_entity_model = NOT_TRACKED
    soft_time_limit_seconds = settings.reconcile_stuck_jobs_soft_time_limit_seconds


@celery_app.task(
    base=_ReconcileStuckJobsCronTask, name="src.worker.tasks.reconcile_stuck_jobs_cron"
)
def reconcile_stuck_jobs_cron() -> None:
    """Celery Beat entry point: fail any job left stuck in IN_PROCESS past the staleness threshold."""
    db = SessionLocal()
    try:
        reconciled = job_service.reconcile_stuck_jobs(db)
        get_logger().info("reconcile_stuck_jobs_cron_completed", reconciled=reconciled)
    finally:
        db.close()


class _DlqDumpTask(TimeLimitedTask):
    """Deliberately NOT DiffpypeTask: on_failure would try to dispatch another
    dlq_dump on failure, risking a self-referential dispatch loop if dlq_dump
    itself is ever persistently broken."""

    soft_time_limit_seconds = settings.dlq_dump_soft_time_limit_seconds


@celery_app.task(base=_DlqDumpTask, name="src.worker.tasks.dlq_dump")
def dlq_dump(failed_task_name: str, task_kwargs: dict, error_msg: str) -> None:
    """Log a permanently failed task payload to the dead letter queue."""
    get_logger().warning(
        "task_dead_lettered",
        failed_task_name=failed_task_name,
        task_kwargs=task_kwargs,
        error_msg=error_msg,
    )


class _DbBackupCronTask(DiffpypeTask):
    tracked_entity_model = NOT_TRACKED
    soft_time_limit_seconds = settings.db_backup_soft_time_limit_seconds


@celery_app.task(base=_DbBackupCronTask, name="src.worker.tasks.db_backup_cron")
def db_backup_cron() -> None:
    """Placeholder for nightly database backup, triggered by Celery Beat."""
    get_logger().info("db_backup_cron_triggered", detail="Nightly backup triggered")


class _CliToolTask(DiffpypeTask):
    tracked_entity_model = NOT_TRACKED
    soft_time_limit_seconds = settings.cli_tool_soft_time_limit_seconds


@celery_app.task(base=_CliToolTask, name="src.worker.tasks.execute_cli_tool")
def execute_cli_tool(job_config_id: int, executable: str) -> None:
    """Execute an external CLI tool using the kwargs stored in JobConfiguration."""
    log = get_logger()
    log.info(
        "execute_cli_tool_started", job_config_id=job_config_id, executable=executable
    )

    db = SessionLocal()
    try:
        job_config = db.get(JobConfiguration, job_config_id)
        assert job_config is not None, f"JobConfiguration {job_config_id} not found"
        cmd_list = build_cli_command(executable, job_config.job_kwargs or {})
        job_config.execution_command = " ".join(cmd_list)
        db.commit()

        result = subprocess.run(cmd_list, capture_output=True, text=True, check=True)
        log.info(
            "execute_cli_tool_completed",
            job_config_id=job_config_id,
            stdout=result.stdout,
        )
    finally:
        db.close()
