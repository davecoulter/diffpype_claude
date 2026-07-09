"""Unit tests for Celery application configuration."""
from unittest.mock import MagicMock

from celery import Celery

from src.worker.celery_app import _configure_beat_schedule


def test_beat_schedule_populated_when_cron_enabled():
    """beat_schedule must contain the nightly backup entry when the toggle is on."""
    app = Celery()
    cfg = MagicMock(enable_db_backup_cron=True)
    _configure_beat_schedule(app, cfg)
    assert "nightly-db-backup" in app.conf.beat_schedule
    assert app.conf.beat_schedule["nightly-db-backup"]["task"] == "src.worker.tasks.db_backup_cron"


def test_beat_schedule_absent_when_cron_disabled():
    """beat_schedule must not be set when the toggle is off."""
    app = Celery()
    cfg = MagicMock(enable_db_backup_cron=False)
    _configure_beat_schedule(app, cfg)
    assert not app.conf.beat_schedule
