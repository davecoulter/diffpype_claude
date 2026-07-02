from pydantic import BaseModel, Field

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


class BaseJobConfig(BaseModel):
    pass


class DummyJobConfig(BaseJobConfig):
    sleep_duration: int = Field(default=5, ge=1, le=10)


class JobSubmitRequest(BaseModel):
    task_name: str
    config: DummyJobConfig
