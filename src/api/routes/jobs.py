from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.api.schemas import JobReconcileRequest, JobReconcileResponse
from src.db.session import get_db
from src.services import job_service

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("/reconcile", response_model=JobReconcileResponse)
def reconcile_stuck_jobs(
    body: JobReconcileRequest, db: Session = Depends(get_db)
) -> JobReconcileResponse:
    """Fail any job stuck IN_PROCESS past the staleness threshold; return what changed."""
    if body.threshold_seconds is not None:
        reconciled = job_service.reconcile_stuck_jobs(db, body.threshold_seconds)
    else:
        reconciled = job_service.reconcile_stuck_jobs(db)
    return JobReconcileResponse(reconciled=reconciled)
