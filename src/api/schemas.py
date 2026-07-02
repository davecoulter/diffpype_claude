from pydantic import BaseModel

from src.db.enums import JobStatus


class JobDispatchResponse(BaseModel):
    job_id: str
    image_id: int


class DummyImageStatus(BaseModel):
    id: int
    status: JobStatus
    latest_job_id: str | None

    model_config = {"from_attributes": True}


class StatusMetadata(BaseModel):
    value: str
    label: str
    color: str
