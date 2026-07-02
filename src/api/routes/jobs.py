from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from src.api.schemas import DummyImageStatus, JobDispatchResponse
from src.db.enums import JobStatus
from src.db.models import DummyImage
from src.db.session import get_db
from src.worker.tasks import sleep_and_update_status

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("/dummy", response_model=JobDispatchResponse)
def create_dummy_job(db: Session = Depends(get_db)) -> JobDispatchResponse:
    image = DummyImage(status=JobStatus.IN_PROCESS)
    db.add(image)
    db.commit()
    db.refresh(image)

    async_result = sleep_and_update_status.delay(image.id)

    image.latest_job_id = async_result.id
    db.commit()

    return JobDispatchResponse(job_id=async_result.id, image_id=image.id)


@router.get("/dummy/{image_id}", response_model=DummyImageStatus)
def get_dummy_job_status(image_id: int, db: Session = Depends(get_db)) -> DummyImageStatus:
    image = db.get(DummyImage, image_id)
    if image is None:
        raise HTTPException(status_code=404, detail="DummyImage not found")
    return DummyImageStatus.model_validate(image)
