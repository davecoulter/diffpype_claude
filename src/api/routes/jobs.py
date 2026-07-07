from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from src.api.schemas import DummyImageStatus, JobDispatchResponse, JobSubmitRequest
from src.db.session import get_db
from src.services import job_service

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("/dummy", response_model=JobDispatchResponse)
def create_dummy_job(
    body: JobSubmitRequest, db: Session = Depends(get_db)
) -> JobDispatchResponse:
    job_id, image_id = job_service.dispatch_dummy_job(db, body.config.model_dump())
    return JobDispatchResponse(job_id=job_id, image_id=image_id)


@router.get("/dummy/{image_id}", response_model=DummyImageStatus)
def get_dummy_job_status(image_id: int, db: Session = Depends(get_db)) -> DummyImageStatus:
    image = job_service.get_dummy_job(db, image_id)
    if image is None:
        raise HTTPException(status_code=404, detail="DummyImage not found")
    return DummyImageStatus.model_validate(image)
