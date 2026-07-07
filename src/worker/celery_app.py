from celery import Celery

from src.core.config import settings
from src.core.logger import configure_logging
from src.db.enums import CeleryQueue

# Configure JSON logging for the worker process (and any CLI path that imports
# the service/task layer) so all components stream structured logs to stdout.
configure_logging()

celery_app = Celery(
    "diffpype",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["src.worker.tasks"],
)

celery_app.conf.task_routes = {
    "src.worker.tasks.sleep_and_update_status": {"queue": CeleryQueue.LIGHT},
}
