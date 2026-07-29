import os
import subprocess
import tempfile
import time

import pandas as pd

from src.core.logger import get_logger
from src.db.enums import JobStatus
from src.db.models import IngestBatch, JobConfiguration, Level3Mosaic
from src.db.session import SessionLocal
from src.services import ingest_service
from src.services.storage_service import get_storage_service
from src.worker.base_task import DiffpypeTask
from src.worker.celery_app import celery_app
from src.worker.utils import build_cli_command


@celery_app.task(name="src.worker.tasks.run_ingest_batch")
def run_ingest_batch(batch_id: int) -> None:
    """Scan an IngestBatch's storage prefix and bulk-upsert Level2Image/Level2Calibration rows.

    Not built on DiffpypeTask: that base's on_failure is entity-agnostic
    (logging + DLQ dispatch only), so it can't transition this batch's row out
    of IN_PROCESS on crash. This task handles its own crash-safety instead,
    guaranteeing no orphaned IN_PROCESS row for the entity it actually tracks.
    """
    log = get_logger()
    log.info("ingest_batch_started", batch_id=batch_id)

    db = SessionLocal()
    try:
        batch = db.get(IngestBatch, batch_id)
        assert batch is not None, f"IngestBatch {batch_id} not found"
        batch.status = JobStatus.IN_PROCESS
        db.commit()

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


@celery_app.task(name="src.worker.tasks.run_mosaic_drizzle")
def run_mosaic_drizzle(mosaic_id: int) -> None:
    """Placeholder drizzle execution: sleeps and transitions to COMPLETE.

    The Level3Mosaic row itself (footprint, barycenter, and its M2M-derived
    constituent calibrations) is already the complete job specification —
    only the actual pixel-level drizzle is deferred, to a future
    JWST-pipeline-specific doc. Not built on DiffpypeTask for the same reason
    as run_ingest_batch: that base's on_failure is entity-agnostic and cannot
    transition this mosaic's row out of IN_PROCESS on crash.
    """
    log = get_logger()
    log.info("mosaic_drizzle_started", mosaic_id=mosaic_id)

    db = SessionLocal()
    try:
        mosaic = db.get(Level3Mosaic, mosaic_id)
        assert mosaic is not None, f"Level3Mosaic {mosaic_id} not found"
        mosaic.status = JobStatus.IN_PROCESS
        db.commit()

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


@celery_app.task(name="src.worker.tasks.dlq_dump")
def dlq_dump(failed_task_name: str, task_kwargs: dict, error_msg: str) -> None:
    """Log a permanently failed task payload to the dead letter queue."""
    get_logger().warning(
        "task_dead_lettered",
        failed_task_name=failed_task_name,
        task_kwargs=task_kwargs,
        error_msg=error_msg,
    )


@celery_app.task(name="src.worker.tasks.db_backup_cron")
def db_backup_cron() -> None:
    """Placeholder for nightly database backup, triggered by Celery Beat."""
    get_logger().info("db_backup_cron_triggered", detail="Nightly backup triggered")


@celery_app.task(base=DiffpypeTask, name="src.worker.tasks.execute_cli_tool")
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
