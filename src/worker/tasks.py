import subprocess
import time

from sqlalchemy import func
from structlog.contextvars import bind_contextvars

from src.core.logger import get_logger
from src.db.enums import JobStatus
from src.db.models import DummyImage, JobConfiguration
from src.db.session import SessionLocal
from src.worker.base_task import DiffpypeTask
from src.worker.celery_app import celery_app
from src.worker.utils import build_cli_command


@celery_app.task(base=DiffpypeTask, name="src.worker.tasks.sleep_and_update_status")
def sleep_and_update_status(
    image_id: int, sleep_duration: int = 5, correlation_id: str | None = None
) -> None:
    bind_contextvars(correlation_id=correlation_id)
    log = get_logger()
    log.info("task_started", image_id=image_id, sleep_duration=sleep_duration)

    # Record the start time in its own short transaction so we do not hold a
    # database connection open across the (potentially long) sleep.
    db = SessionLocal()
    try:
        image = db.get(DummyImage, image_id)
        image.job_started_at = func.now()
        db.commit()
    finally:
        db.close()

    time.sleep(sleep_duration)

    db = SessionLocal()
    try:
        image = db.get(DummyImage, image_id)
        image.status = JobStatus.COMPLETE
        image.job_finished_at = func.now()
        db.commit()
    finally:
        db.close()

    log.info("task_completed", image_id=image_id)


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
def execute_cli_tool(
    job_config_id: int, executable: str, correlation_id: str | None = None
) -> None:
    """Execute an external CLI tool using the kwargs stored in JobConfiguration."""
    bind_contextvars(correlation_id=correlation_id)
    log = get_logger()
    log.info("execute_cli_tool_started", job_config_id=job_config_id, executable=executable)

    db = SessionLocal()
    try:
        job_config = db.get(JobConfiguration, job_config_id)
        cmd_list = build_cli_command(executable, job_config.job_kwargs or {})
        job_config.execution_command = " ".join(cmd_list)
        db.commit()

        result = subprocess.run(cmd_list, capture_output=True, text=True, check=True)
        log.info("execute_cli_tool_completed", job_config_id=job_config_id, stdout=result.stdout)
    finally:
        db.close()
