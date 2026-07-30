"""Shared job-provenance and stuck-job-reconciliation service for API and CLI.

Two responsibilities live here:

* ``create_job_configuration`` — the single place a dispatch path records its
  provenance (``task_name`` + ``job_kwargs`` + owning user) as a
  ``JobConfiguration`` row, linked from the tracked entity it dispatches.
* ``reconcile_stuck_jobs`` — the watchdog that fails any tracked job left in
  ``IN_PROCESS`` past its staleness threshold (an uncatchable worker crash / OOM
  kill can't run the task's own ``except`` block, so the row would otherwise sit
  ``IN_PROCESS`` forever).
"""

from datetime import datetime, timezone
from typing import cast

import sqlalchemy as sa
from sqlalchemy.orm import Session

from src.core.config import settings
from src.db.enums import JobStatus
from src.db.models import IngestBatch, JobConfiguration, Level3Mosaic

# Static registry of the job entities the watchdog reconciles. Each shares the
# same tracked columns: ``status`` (JobStatus), ``updated_at`` (staleness clock),
# and ``job_configuration`` (per-job override source). Add an entity here to
# bring it under the watchdog.
_STUCK_JOB_ENTITIES = (IngestBatch, Level3Mosaic)


def create_job_configuration(
    db: Session,
    user_id: int,
    task_name: str,
    job_kwargs: dict | None = None,
) -> JobConfiguration:
    """Create and flush a JobConfiguration provenance row, returning it with its id assigned.

    Flushed (not committed) so it participates in the caller's transaction — the
    dispatch path commits it atomically with the tracked entity row it links to.
    """
    job_config = JobConfiguration(
        user_id=user_id, task_name=task_name, job_kwargs=job_kwargs
    )
    db.add(job_config)
    db.flush()
    return job_config


def reconcile_stuck_jobs(
    db: Session,
    staleness_timeout_seconds: int = settings.job_staleness_timeout_seconds,
) -> list[dict]:
    """Fail every tracked job stuck IN_PROCESS past its staleness threshold; return what changed.

    Honors a per-job ``staleness_timeout_seconds`` override in the linked
    ``JobConfiguration.job_kwargs`` over the global default. Calls ``db.rollback()``
    first so a prior failed transaction on this session can't poison the status
    writes (mirrors the framework error-handler pattern).
    """
    db.rollback()
    now = datetime.now(timezone.utc)
    reconciled: list[dict] = []

    for model in _STUCK_JOB_ENTITIES:
        rows = (
            db.execute(sa.select(model).where(model.status == JobStatus.IN_PROCESS))
            .scalars()
            .all()
        )
        for raw_row in rows:
            # Both registered entities share these columns (status/updated_at/id
            # via TimestampMixin, plus job_configuration); the cast tells the type
            # checker that, since the registry widens the row to the ORM Base.
            row = cast("IngestBatch | Level3Mosaic", raw_row)
            timeout = staleness_timeout_seconds
            job_config = row.job_configuration
            if job_config is not None and job_config.job_kwargs:
                override = job_config.job_kwargs.get("staleness_timeout_seconds")
                if override is not None:
                    timeout = override
            age_seconds = (now - row.updated_at).total_seconds()
            if age_seconds > timeout:
                row.status = JobStatus.FAILED
                reconciled.append(
                    {
                        "entity": model.__name__,
                        "id": row.id,
                        "age_seconds": age_seconds,
                    }
                )

    db.commit()
    return reconciled
