from fastapi import APIRouter

from src.api.schemas import StorageSyncRequest, StorageSyncResponse
from src.services import storage_service

router = APIRouter(prefix="/storage", tags=["storage"])


@router.post("/sync", response_model=StorageSyncResponse)
def sync_storage(body: StorageSyncRequest) -> StorageSyncResponse:
    """Dispatch a staging→canonical storage sync Celery task and return its job id."""
    job_id = storage_service.dispatch_staging_sync(
        body.staging_location, body.canonical_prefix
    )
    return StorageSyncResponse(job_id=job_id)
