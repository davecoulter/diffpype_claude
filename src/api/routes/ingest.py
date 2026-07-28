from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from src.api.schemas import IngestBatchStatus, IngestDispatchResponse, IngestRequest
from src.db.session import get_db
from src.services import ingest_service

router = APIRouter(prefix="/ingest", tags=["ingest"])


@router.post("", response_model=IngestDispatchResponse)
def create_ingest_batch(
    body: IngestRequest, db: Session = Depends(get_db)
) -> IngestDispatchResponse:
    job_id, batch_id = ingest_service.create_ingest_batch(
        db, body.project_id, body.s3_prefix
    )
    return IngestDispatchResponse(job_id=job_id, batch_id=batch_id)


@router.get("/{batch_id}", response_model=IngestBatchStatus)
def get_ingest_batch_status(
    batch_id: int, db: Session = Depends(get_db)
) -> IngestBatchStatus:
    batch = ingest_service.get_ingest_batch(db, batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="IngestBatch not found")
    return IngestBatchStatus.model_validate(batch)
