"""Business logic for temporal (MJD) clustering, persistence, and association.

Isolates the clustering math (``cluster_epochs``) from persistence
(``create_epochs``, the one synchronous write path), matching tile_service's
compute/persist split.
"""

from collections.abc import Sequence

import numpy as np
import pandas as pd
import sqlalchemy as sa
from astropy.time import Time
from scipy.signal import find_peaks
from sklearn.cluster import KMeans
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from src.db.models import (
    Epoch,
    Level2Calibration,
    Level2Image,
    epoch_level2_calibration_association,
    tile_level2_calibration_association,
)


def _fetch_calibration_mjds(
    db: Session, project_id: int, tile_id: int, band_id: int
) -> pd.DataFrame:
    """Query the MJDs of Level2Calibration rows tied to a tile (spatially) and a band."""
    stmt = (
        sa.select(Level2Calibration.id, Level2Image.mjd_avg)
        .join(Level2Image, Level2Calibration.level2_image_id == Level2Image.id)
        .join(
            tile_level2_calibration_association,
            tile_level2_calibration_association.c.level2_calibration_id
            == Level2Calibration.id,
        )
        .where(
            Level2Calibration.project_id == project_id,
            tile_level2_calibration_association.c.tile_id == tile_id,
            Level2Image.band_id == band_id,
            Level2Image.mjd_avg.isnot(None),
        )
    )
    rows = db.execute(stmt).all()
    return pd.DataFrame(rows, columns=["level2_calibration_id", "mjd_avg"])


def _cluster_mjds(mjd_list: list[float], peak_distance_thresh: float) -> np.ndarray:
    """Cluster MJDs into [start, end] epoch intervals via peak-finding + KMeans.

    Pure computation, ports the prototype's ``CreateEpochsFromMJDs``. Guards
    against zero detected peaks (which the prototype did not: an all-flat MJD
    histogram would otherwise call ``KMeans(n_clusters=0)`` and crash) by
    falling back to a single cluster.
    """
    mjd = np.array(mjd_list)
    mjd_reshaped = mjd.reshape(-1, 1)

    nbins = (int(np.ceil(mjd.max())) - int(np.floor(mjd.min()))) + 2
    hist, _ = np.histogram(mjd, bins=nbins, range=(mjd.min() - 1, mjd.max() + 1))
    peaks, _ = find_peaks(hist, height=None, distance=peak_distance_thresh)
    num_clusters = max(len(peaks), 1)

    kmeans = KMeans(n_clusters=num_clusters, random_state=0)
    kmeans.fit(mjd_reshaped)

    cluster_centers = np.sort(kmeans.cluster_centers_.flatten())
    return np.asarray(
        [
            [
                int(np.floor(center - peak_distance_thresh)),
                int(np.ceil(center + peak_distance_thresh)),
            ]
            for center in cluster_centers
        ]
    )


def cluster_epochs(
    db: Session,
    project_id: int,
    tile_id: int,
    band_id: int,
    peak_distance_thresh: float,
) -> list[dict]:
    """Cluster a tile+band's calibration MJDs into epoch dicts. Queries MJDs, writes nothing.

    Returns plain dicts (start_date, end_date, start_mjd, end_mjd, tile_id,
    band_id) — the API/CLI boundary wraps each into an ``EpochCreate``.
    """
    df = _fetch_calibration_mjds(db, project_id, tile_id, band_id)
    if df.empty:
        return []

    intervals = _cluster_mjds(df["mjd_avg"].tolist(), peak_distance_thresh)

    return [
        {
            "start_mjd": float(lo),
            "end_mjd": float(hi),
            "start_date": Time(float(lo), format="mjd").datetime,
            "end_date": Time(float(hi), format="mjd").datetime,
            "tile_id": tile_id,
            "band_id": band_id,
        }
        for lo, hi in intervals
    ]


def create_epochs(db: Session, project_id: int, epochs: list[dict]) -> list[Epoch]:
    """Bulk-insert Epoch rows and associate each with calibrations whose MJD falls in its range."""
    if not epochs:
        return []

    rows = [{**epoch, "project_id": project_id} for epoch in epochs]
    created = db.execute(sa.insert(Epoch).returning(Epoch), rows).scalars().all()
    db.flush()

    _associate_epochs_with_calibrations_in_range(db, project_id, created)
    db.commit()
    return list(created)


def _associate_epochs_with_calibrations_in_range(
    db: Session, project_id: int, epochs: Sequence[Epoch]
) -> None:
    """Populate epoch_level2_calibration_association for each epoch's tile+band+MJD range.

    Scoped to the epoch's own tile (via the same spatial association tile_service
    already populated) and band, not just project+MJD — an Epoch is defined as a
    temporal grouping for one specific Tile and Band (see the Epoch model's
    docstring), so an unscoped MJD-only match would wrongly link calibrations
    from an unrelated tile or band whose MJD happens to overlap.
    """
    association_rows: list[dict] = []
    for epoch in epochs:
        stmt = (
            sa.select(Level2Calibration.id)
            .join(Level2Image, Level2Calibration.level2_image_id == Level2Image.id)
            .join(
                tile_level2_calibration_association,
                tile_level2_calibration_association.c.level2_calibration_id
                == Level2Calibration.id,
            )
            .where(
                Level2Calibration.project_id == project_id,
                tile_level2_calibration_association.c.tile_id == epoch.tile_id,
                Level2Image.band_id == epoch.band_id,
                Level2Image.mjd_avg.isnot(None),
                Level2Image.mjd_avg >= epoch.start_mjd,
                Level2Image.mjd_avg <= epoch.end_mjd,
            )
        )
        association_rows.extend(
            {"epoch_id": epoch.id, "level2_calibration_id": cal_id}
            for (cal_id,) in db.execute(stmt).all()
        )

    if association_rows:
        db.execute(
            pg_insert(epoch_level2_calibration_association)
            .values(association_rows)
            .on_conflict_do_nothing(
                index_elements=["epoch_id", "level2_calibration_id"]
            )
        )
