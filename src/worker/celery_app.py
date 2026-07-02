import os

from celery import Celery

from src.db.enums import CeleryQueue

REDIS_URL = os.environ["REDIS_URL"]

celery_app = Celery(
    "diffpype",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["src.worker.tasks"],
)

celery_app.conf.task_routes = {
    "src.worker.tasks.sleep_and_update_status": {"queue": CeleryQueue.LIGHT},
}
