"""Celery base task providing the framework Boundary Pattern.

``DiffpypeTask.on_failure`` is the outer backstop for any exception that bubbles
out of a task body. It is deliberately entity-agnostic: it logs the crash with
structlog and dispatches the failed payload to the dead-letter queue, but does
not write any domain entity's status. Tasks that track a domain row (e.g.
``run_ingest_batch``, ``run_mosaic_drizzle``) own their own crash-safe FAILED
transition inside the task body; entities orphaned in ``IN_PROCESS`` by an
uncatchable crash (SIGKILL/OOM, where ``on_failure`` never runs at all) are
reconciled by the stuck-job watchdog (doc 30).
"""

import celery
from sqlalchemy.exc import OperationalError as SAOperationalError

from src.core.config import settings
from src.core.logger import get_logger


class DiffpypeTask(celery.Task):
    """Base task that guarantees failure logging and dead-letter dispatch."""

    # Include SAOperationalError so transient DB connection drops are retried,
    # not just raw socket-level IOError/ConnectionError.
    autoretry_for = (
        IOError,
        OSError,
        ConnectionError,
        TimeoutError,
        SAOperationalError,
    )
    max_retries = settings.celery_task_max_retries
    default_retry_delay = settings.celery_task_retry_delay

    def on_failure(self, exc, task_id, args, kwargs, einfo) -> None:
        # The active OTel task span supplies the correlation_id to every log line
        # via the structlog processor, so no manual context binding is needed here.
        log = get_logger()
        log.error(
            "task_failed",
            task_id=task_id,
            args=args,
            error=str(exc),
            exc_info=einfo,
        )

        # DLQ dispatch (Redis-only) always fires so the failed payload is never
        # silently lost. No domain-entity status write happens here — see the
        # module docstring for why on_failure is intentionally entity-agnostic.
        try:
            from src.worker.tasks import (
                dlq_dump,
            )  # lazy import avoids circular dependency

            dlq_dump.apply_async(
                kwargs={
                    "failed_task_name": self.name or task_id,
                    "task_kwargs": kwargs,
                    "error_msg": str(exc),
                },
                queue="dead_letter",
            )
        except Exception:
            log.error("on_failure_dlq_dispatch_failed", task_id=task_id, exc_info=True)
