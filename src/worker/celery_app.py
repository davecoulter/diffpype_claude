import os

from celery import Celery

from src.core.logger import configure_logging
from src.db.enums import CeleryQueue

# Configure JSON logging for the worker process (and any CLI path that imports
# the service/task layer) so all components stream structured logs to stdout.
configure_logging()

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
