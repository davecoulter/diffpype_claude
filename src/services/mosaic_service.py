"""Business logic for mosaic job-metadata creation: footprint union + barycenter.

A Level3Mosaic row is real job metadata, not a placeholder: once created with
its real (tile, epoch, band, instrument, project) combination, it *is* the
complete job specification a future drizzle pipeline queries via the M2M
association tables to find its constituent Level2Calibrations. The pixel-level
drizzle itself is deferred to a future JWST-pipeline doc.
"""

import sqlalchemy as sa
from mocpy import MOC
from sqlalchemy.orm import Session

from src.core.logger import get_logger
from src.db.enums import JobStatus
from src.db.models import (
    Level2Calibration,
    Level2Image,
    Level3Mosaic,
    epoch_level2_calibration_association,
    tile_level2_calibration_association,
)


def _unioned_footprint_and_barycenter(mocs: list[MOC]) -> tuple[MOC, float, float]:
    """Union a list of MOCs and return (union, ra_barycenter_deg, decl_barycenter_deg).

    Ports the prototype's ``Get_Unioned_MOC``, plus barycenter extraction —
    addresses GitHub issue #27 in the same write path that already has to
    compute the union.
    """
    union = mocs[0]
    for moc in mocs[1:]:
        union = union.union(moc)
    barycenter = union.barycenter()
    return union, float(barycenter.ra.degree), float(barycenter.dec.degree)


def _fetch_constituent_footprints(
    db: Session, project_id: int, tile_id: int, epoch_id: int, band_id: int
) -> list[MOC]:
    """Return footprints of Level2Calibrations linked to both this tile and this epoch, for this band.

    The M2M association tables (populated by tile_service/epoch_service) are
    the source of truth for "which calibrations make up this mosaic" — this
    mirrors exactly the query a future orchestrator would run to construct the
    real drizzle job's input file list.
    """
    stmt = (
        sa.select(Level2Calibration.footprint)
        .join(Level2Image, Level2Calibration.level2_image_id == Level2Image.id)
        .join(
            tile_level2_calibration_association,
            tile_level2_calibration_association.c.level2_calibration_id
            == Level2Calibration.id,
        )
        .join(
            epoch_level2_calibration_association,
            epoch_level2_calibration_association.c.level2_calibration_id
            == Level2Calibration.id,
        )
        .where(
            Level2Calibration.project_id == project_id,
            tile_level2_calibration_association.c.tile_id == tile_id,
            epoch_level2_calibration_association.c.epoch_id == epoch_id,
            Level2Image.band_id == band_id,
            Level2Calibration.footprint.isnot(None),
        )
    )
    return [row[0] for row in db.execute(stmt).all()]


def create_mosaic(
    db: Session,
    project_id: int,
    tile_id: int,
    epoch_id: int,
    band_id: int,
    instrument_id: int,
    filename: str,
    target_plate_scale: float,
) -> tuple[str, int]:
    """Create a Level3Mosaic with its computed footprint/barycenter, dispatch the drizzle task.

    Returns (job_id, mosaic_id).
    """
    from src.worker.tasks import run_mosaic_drizzle  # lazy: avoids a circular import

    footprints = _fetch_constituent_footprints(
        db, project_id, tile_id, epoch_id, band_id
    )
    footprint = ra = decl = None
    if footprints:
        footprint, ra, decl = _unioned_footprint_and_barycenter(footprints)

    mosaic = Level3Mosaic(
        filename=filename,
        target_plate_scale=target_plate_scale,
        footprint=footprint,
        ra=ra,
        decl=decl,
        instrument_id=instrument_id,
        band_id=band_id,
        epoch_id=epoch_id,
        tile_id=tile_id,
        project_id=project_id,
        status=JobStatus.PENDING,
    )
    db.add(mosaic)
    db.commit()
    db.refresh(mosaic)

    try:
        async_result = run_mosaic_drizzle.delay(mosaic.id)
    except Exception:
        get_logger().error("mosaic_dispatch_failed", mosaic_id=mosaic.id, exc_info=True)
        mosaic.status = JobStatus.FAILED
        db.commit()
        raise

    get_logger().info(
        "mosaic_dispatched", mosaic_id=mosaic.id, job_id=async_result.id
    )
    return async_result.id, mosaic.id


def get_mosaic(db: Session, mosaic_id: int) -> Level3Mosaic | None:
    """Return the Level3Mosaic with the given primary key, or None if not found."""
    return db.get(Level3Mosaic, mosaic_id)
