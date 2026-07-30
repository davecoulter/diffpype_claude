"""Celery base task providing the framework Boundary Pattern.

``DiffpypeTask.on_failure`` is the outer backstop for any exception that bubbles
out of a task body. It is deliberately entity-agnostic: it logs the crash with
structlog and dispatches the failed payload to the dead-letter queue, but does
not write any domain entity's status. Tasks that track a domain row (e.g.
``run_ingest_batch``, ``run_mosaic_drizzle``) use ``begin_tracked_job`` for their
crash-safe ``IN_PROCESS``/stale-redelivery handling; entities orphaned in
``IN_PROCESS`` by an uncatchable crash (SIGKILL/OOM, where ``on_failure`` never
runs at all) are reconciled by the stuck-job watchdog (doc 30).

Every concrete task in this app must declare an explicit time ceiling and
(if applicable) which watchdog-tracked entity it owns — see ``TimeLimitedTask``
and ``DiffpypeTask`` below. Both contracts are enforced via ``__init_subclass__``
checking ``cls.__dict__`` (never ``getattr``), so a task that accidentally
subclasses another concrete task instead of the real base — silently inheriting
its ceiling/tracked entity — is rejected at class-definition time rather than
quietly doing the wrong thing. (Verified empirically during design: a plain
``abc.ABC``/``abstractmethod`` does *not* catch this specific mistake, since ABC
only requires a concrete value to exist somewhere in the MRO, not that the
subclass itself declared it.)
"""

import celery
from sqlalchemy.exc import OperationalError as SAOperationalError
from sqlalchemy.orm import Session

from src.core.config import settings
from src.core.logger import get_logger
from src.db.enums import JobStatus
from src.db.models import Base


class NotTracked:
    """Sentinel: this task deliberately does not own a watchdog-tracked entity."""

    def __repr__(self) -> str:
        return "NOT_TRACKED"


NOT_TRACKED = NotTracked()
"""Explicit ``tracked_entity_model`` value for tasks with no tracked entity — a
real, distinct value (never bare ``None``) so "deliberately untracked" can't be
confused with "the developer forgot to declare this"."""

HARD_LIMIT_BUFFER_SECONDS = 30
"""Grace window between a task's soft and hard time limit, giving
``SoftTimeLimitExceeded`` cleanup code (e.g. killing a subprocess) a chance to
run before Celery forcibly kills the task outright. Reused by ``celery_app.py``
to compute ``broker_transport_options["visibility_timeout"]`` from the same
real, enforced ceilings, rather than duplicating the number."""


class TimeLimitedTask(celery.Task):
    """Requires every concrete subclass to declare its own ``soft_time_limit_seconds``.

    ``abstract = True`` follows Celery's own convention for a non-registered
    intermediate base, exempting it (and any other abstract base) from its own
    contract. A missing declaration on a concrete subclass raises ``TypeError``
    at class-definition time (Celery's ``@app.task(base=...)`` decorator
    dynamically creates a real subclass per task, so this fires no later than
    worker/beat startup).
    """

    abstract = True

    def __init_subclass__(cls, **kwargs) -> None:
        super().__init_subclass__(**kwargs)
        if cls.__dict__.get("abstract", False) or cls.__dict__.get("_decorated", False):
            # `_decorated` is set by Celery's own `_task_from_fun` on the dynamic
            # wrapper subclass it creates for every `@app.task(...)`-decorated
            # function (`type(fun.__name__, (base,), {"_decorated": True, ...})`)
            # — this is Celery's own internal wrapping, not a human-authored
            # subclass, so it's legitimately exempt: it inherits from whatever
            # `base=` was passed, which has already satisfied this contract.
            return
        if "soft_time_limit_seconds" not in cls.__dict__:
            raise TypeError(
                f"{cls.__name__} must declare its own soft_time_limit_seconds "
                "(never inherited from a parent class)."
            )

    @property
    def soft_time_limit(self) -> int:
        return self.soft_time_limit_seconds

    @property
    def time_limit(self) -> int:
        return self.soft_time_limit_seconds + HARD_LIMIT_BUFFER_SECONDS


class DiffpypeTask(TimeLimitedTask):
    """Base task guaranteeing failure logging, dead-letter dispatch, and (for
    tracked tasks) crash-safe, stale-redelivery-proof entity transitions."""

    abstract = True

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

    def __init_subclass__(cls, **kwargs) -> None:
        super().__init_subclass__(**kwargs)
        if cls.__dict__.get("abstract", False) or cls.__dict__.get("_decorated", False):
            return  # see TimeLimitedTask.__init_subclass__ for why `_decorated` is exempt
        if "tracked_entity_model" not in cls.__dict__:
            raise TypeError(
                f"{cls.__name__} must declare tracked_entity_model explicitly "
                "(a real model, or base_task.NOT_TRACKED) — never inherited."
            )

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

    def begin_tracked_job(self, db: Session, entity_id: int) -> Base | None:
        """Fetch this task's declared tracked entity and transition it to
        IN_PROCESS — unless it's already resolved (a stale redelivery arriving
        after the stuck-job watchdog already gave up on it), in which case log
        the skip and return None. The caller must bail without doing any work
        when this returns None; this is what prevents a late, uncoordinated
        Celery/Redis redelivery from silently reviving or overwriting a job the
        watchdog already marked FAILED.
        """
        if self.tracked_entity_model is NOT_TRACKED:
            raise TypeError(
                f"{type(self).__name__} declared NOT_TRACKED; cannot call begin_tracked_job"
            )
        entity = db.get(self.tracked_entity_model, entity_id)
        assert (
            entity is not None
        ), f"{self.tracked_entity_model.__name__} {entity_id} not found"
        if entity.status in (JobStatus.COMPLETE, JobStatus.FAILED):
            get_logger().warning(
                "tracked_job_stale_redelivery_skipped",
                entity=self.tracked_entity_model.__name__,
                id=entity_id,
                status=entity.status.value,
            )
            return None
        entity.status = JobStatus.IN_PROCESS
        db.commit()
        return entity
