"""Unit tests for Celery application configuration."""

from unittest.mock import MagicMock

from celery import Celery

from src.core.config import settings
from src.worker.base_task import HARD_LIMIT_BUFFER_SECONDS
from src.worker.celery_app import (
    VISIBILITY_TIMEOUT_SECONDS,
    _configure_beat_schedule,
    celery_app,
)


def test_beat_schedule_populated_when_cron_enabled():
    """beat_schedule must contain the nightly backup entry when the toggle is on."""
    app = Celery()
    cfg = MagicMock(enable_db_backup_cron=True)
    _configure_beat_schedule(app, cfg)
    assert "nightly-db-backup" in app.conf.beat_schedule
    assert (
        app.conf.beat_schedule["nightly-db-backup"]["task"]
        == "src.worker.tasks.db_backup_cron"
    )


def test_beat_schedule_absent_when_cron_disabled():
    """beat_schedule must not be set when the toggle is off."""
    app = Celery()
    cfg = MagicMock(enable_db_backup_cron=False)
    _configure_beat_schedule(app, cfg)
    assert not app.conf.beat_schedule


def test_visibility_timeout_is_at_least_the_largest_task_hard_time_limit():
    """visibility_timeout must never be shorter than any task's own enforced
    hard time_limit — otherwise Redis could redeliver a still-healthy,
    legitimately-running task to a second worker concurrently (doc 30 §3a)."""
    largest_soft_limit = max(
        settings.staging_sync_soft_time_limit_seconds,
        settings.ingest_batch_soft_time_limit_seconds,
        settings.mosaic_drizzle_soft_time_limit_seconds,
        settings.cli_tool_soft_time_limit_seconds,
        settings.db_backup_soft_time_limit_seconds,
        settings.dlq_dump_soft_time_limit_seconds,
        settings.reconcile_stuck_jobs_soft_time_limit_seconds,
    )
    largest_hard_limit = largest_soft_limit + HARD_LIMIT_BUFFER_SECONDS
    assert VISIBILITY_TIMEOUT_SECONDS > largest_hard_limit


def test_broker_transport_options_configured_on_the_real_app():
    assert (
        celery_app.conf.broker_transport_options["visibility_timeout"]
        == VISIBILITY_TIMEOUT_SECONDS
    )
