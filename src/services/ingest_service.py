"""Business logic for scanning a storage prefix and ingesting FITS headers.

Pandas stays entirely inside this module (``parse_fits_headers`` and its
callers here) — it never crosses the API/CLI/Celery boundary, matching the
project's object-model convention: Pydantic at every boundary, pandas only
as an internal computation detail.
"""

import os

import numpy as np
import pandas as pd
import sqlalchemy as sa
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.time import Time
from astropy.wcs import WCS
from astropy.wcs.utils import proj_plane_pixel_scales
from mocpy import MOC
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from src.core.logger import get_logger
from src.db.enums import JobStatus
from src.db.models import Band, IngestBatch, Instrument, Level2Calibration, Level2Image

# HEALPix order used for per-image footprints computed from a WCS polygon — matches
# the prototype's ported convention for detector-scale (not all-sky-tile-scale)
# precision. spatial_types.MOCType normalizes any input depth to depth 29 on
# persistence, so this only affects computation precision, not storage.
_FOOTPRINT_MAX_DEPTH = 21


def parse_fits_headers(local_paths: list[str]) -> pd.DataFrame:
    """Extract Level2Image/Level2Calibration fields from local FITS files into a DataFrame.

    One row per file. ``instrument_name``/``band_name`` are the raw header strings
    (INSTRUME/FILTER); resolving them to Instrument/Band ids is a separate,
    DB-touching step so this function stays a pure, file-in/DataFrame-out unit.
    """
    rows = []
    for path in local_paths:
        h_sci = fits.getheader(path, "SCI")
        h_pri = fits.getheader(path, "PRIMARY")
        wcs = WCS(h_sci)

        footprint_deg = wcs.calc_footprint()
        sky_poly = SkyCoord(footprint_deg, unit="deg", frame="icrs")
        moc = MOC.from_polygon_skycoord(
            sky_poly, complement=False, max_depth=_FOOTPRINT_MAX_DEPTH
        )
        plate_scale = float(np.mean(proj_plane_pixel_scales(wcs)) * 3600.0)

        mjd_avg = float(h_sci["MJD-AVG"])
        base_filename = os.path.basename(path)

        rows.append(
            {
                "base_filename": base_filename,
                "current_file_ext": os.path.splitext(base_filename)[-1],
                "ra": float(h_sci["CRVAL1"]),
                "decl": float(h_sci["CRVAL2"]),
                "exp_time": float(h_sci["XPOSURE"]),
                "mjd_avg": mjd_avg,
                "target_name": h_pri["TARGPROP"],
                "obs_start": Time(mjd_avg, format="mjd").datetime,
                "instrument_name": h_pri["INSTRUME"],
                "band_name": h_pri["FILTER"],
                "plate_scale": plate_scale,
                "footprint": moc,
            }
        )
    return pd.DataFrame(rows)


def _resolve_reference_ids(db: Session, df: pd.DataFrame) -> pd.DataFrame:
    """Replace instrument_name/band_name columns with instrument_id/band_id via DB lookup.

    Matched case-insensitively: real FITS headers conventionally write
    INSTRUME/FILTER in uppercase (e.g. "NIRCAM"), which doesn't necessarily
    match this project's reference data naming convention (e.g. "NIRCam").
    """
    instrument_ids = {i.name.upper(): i.id for i in db.query(Instrument).all()}
    band_ids = {b.name.upper(): b.id for b in db.query(Band).all()}

    df = df.copy()
    df["instrument_id"] = df["instrument_name"].str.upper().map(instrument_ids)
    df["band_id"] = df["band_name"].str.upper().map(band_ids)

    missing = df[df["instrument_id"].isna() | df["band_id"].isna()]
    if not missing.empty:
        raise ValueError(
            "Unknown instrument/band for files: " f"{missing['base_filename'].tolist()}"
        )

    df["instrument_id"] = df["instrument_id"].astype(int)
    df["band_id"] = df["band_id"].astype(int)
    return df.drop(columns=["instrument_name", "band_name"])


def bulk_upsert_images_and_calibrations(
    db: Session, project_id: int, df: pd.DataFrame
) -> int:
    """Bulk upsert Level2Image + project-scoped Level2Calibration rows from a parsed DataFrame.

    Idempotent: re-ingesting an already-ingested base_filename/project pair is a
    safe no-op via ON CONFLICT DO NOTHING on both tables' unique constraints.
    Returns the number of rows processed from ``df``.
    """
    if df.empty:
        return 0

    df = _resolve_reference_ids(db, df)

    image_columns = [
        "base_filename",
        "ra",
        "decl",
        "exp_time",
        "mjd_avg",
        "target_name",
        "obs_start",
        "instrument_id",
        "band_id",
    ]
    image_rows = df[image_columns].to_dict("records")
    db.execute(
        pg_insert(Level2Image)
        .values(image_rows)
        .on_conflict_do_nothing(index_elements=["base_filename"])
    )
    db.flush()

    base_filenames = df["base_filename"].tolist()
    image_ids = {
        row.base_filename: row.id
        for row in db.execute(
            sa.select(Level2Image.id, Level2Image.base_filename).where(
                Level2Image.base_filename.in_(base_filenames)
            )
        ).all()
    }

    calibration_rows = [
        {
            "level2_image_id": image_ids[record["base_filename"]],
            "project_id": project_id,
            "footprint": record["footprint"],
            "current_file_ext": record["current_file_ext"],
            "plate_scale": record["plate_scale"],
            "status": JobStatus.COMPLETE,
        }
        for record in df.to_dict("records")
    ]
    db.execute(
        pg_insert(Level2Calibration)
        .values(calibration_rows)
        .on_conflict_do_nothing(index_elements=["level2_image_id", "project_id"])
    )
    db.commit()
    return len(df)


def create_ingest_batch(
    db: Session, project_id: int, s3_prefix: str
) -> tuple[str, int]:
    """Persist a PENDING IngestBatch, dispatch the ingest Celery task, return (job_id, batch_id)."""
    from src.worker.tasks import run_ingest_batch  # lazy: avoids a circular import

    batch = IngestBatch(
        project_id=project_id, s3_prefix=s3_prefix, status=JobStatus.PENDING
    )
    db.add(batch)
    db.commit()
    db.refresh(batch)

    try:
        async_result = run_ingest_batch.delay(batch.id)
    except Exception:
        get_logger().error(
            "ingest_batch_dispatch_failed", batch_id=batch.id, exc_info=True
        )
        batch.status = JobStatus.FAILED
        db.commit()
        raise

    get_logger().info(
        "ingest_batch_dispatched", batch_id=batch.id, job_id=async_result.id
    )
    return async_result.id, batch.id


def get_ingest_batch(db: Session, batch_id: int) -> IngestBatch | None:
    """Return the IngestBatch with the given primary key, or None if not found."""
    return db.get(IngestBatch, batch_id)
