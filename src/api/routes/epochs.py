from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.api.schemas import EpochBulkCreateRequest, EpochClusterRequest, EpochCreate, EpochRead
from src.db.session import get_db
from src.services import epoch_service

router = APIRouter(prefix="/epochs", tags=["epochs"])


@router.post("/cluster", response_model=list[EpochCreate])
def cluster_epochs(
    body: EpochClusterRequest, db: Session = Depends(get_db)
) -> list[EpochCreate]:
    epochs = epoch_service.cluster_epochs(
        db, body.project_id, body.tile_id, body.band_id, body.peak_distance_thresh
    )
    return [EpochCreate(**e) for e in epochs]


@router.post("", response_model=list[EpochRead])
def create_epochs(
    body: EpochBulkCreateRequest, db: Session = Depends(get_db)
) -> list[EpochRead]:
    epoch_dicts = [e.model_dump() for e in body.epochs]
    created = epoch_service.create_epochs(db, body.project_id, epoch_dicts)
    return [EpochRead.model_validate(e) for e in created]
