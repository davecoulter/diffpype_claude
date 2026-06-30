import os

from celery import Celery

REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")

celery_app = Celery(
    "diffpype",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["src.worker.tasks"],
)

celery_app.conf.task_routes = {
    "src.worker.tasks.sleep_and_update_status": {"queue": "light"},
}
