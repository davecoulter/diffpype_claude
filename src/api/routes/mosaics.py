from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from src.api.schemas import MosaicCreate, MosaicDispatchResponse, MosaicStatus
from src.db.session import get_db
from src.services import mosaic_service

router = APIRouter(prefix="/mosaics", tags=["mosaics"])


@router.post("", response_model=MosaicDispatchResponse)
def create_mosaic(
    body: MosaicCreate, db: Session = Depends(get_db)
) -> MosaicDispatchResponse:
    job_id, mosaic_id = mosaic_service.create_mosaic(
        db,
        body.project_id,
        body.tile_id,
        body.epoch_id,
        body.band_id,
        body.instrument_id,
        body.filename,
        body.target_plate_scale,
    )
    return MosaicDispatchResponse(job_id=job_id, mosaic_id=mosaic_id)


@router.get("/{mosaic_id}", response_model=MosaicStatus)
def get_mosaic_status(mosaic_id: int, db: Session = Depends(get_db)) -> MosaicStatus:
    mosaic = mosaic_service.get_mosaic(db, mosaic_id)
    if mosaic is None:
        raise HTTPException(status_code=404, detail="Level3Mosaic not found")
    return MosaicStatus.model_validate(mosaic)
