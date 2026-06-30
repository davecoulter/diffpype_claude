from pydantic import BaseModel


class JobDispatchResponse(BaseModel):
    job_id: str
    image_id: int


class DummyImageStatus(BaseModel):
    id: int
    status: str
    latest_job_id: str | None

    model_config = {"from_attributes": True}
