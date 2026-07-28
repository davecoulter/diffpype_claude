"""Business logic for tile tessellation, persistence, and spatial association.

Isolates the MOC tessellation math (``generate_tile_tessellation``, a pure
function with no DB access) from persistence (``create_tiles``, the one
synchronous write path) so the tessellation can be previewed without writing,
regardless of whether the tile list came from the tessellation math below or
a future hand-drawn UI widget.
"""

import math
from collections.abc import Sequence

import astropy.units as u
import numpy as np
import sqlalchemy as sa
from astropy.coordinates import SkyCoord
from mocpy import MOC
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from src.db.models import Level2Calibration, Tile, tile_level2_calibration_association
from src.db.spatial_types import MOCType

# HEALPix order for generated tile footprints, matching the prototype's ported
# convention for tile-scale (not detector-scale) precision. MOCType normalizes
# any input depth to depth 29 on persistence, so this only affects computation.
_TILE_FOOTPRINT_MAX_DEPTH = 21


def generate_tile_tessellation(
    tile_side_length_arc_min: float,
    moc_to_tile: MOC,
    overlap_in_arc_min: float = 0.0,
) -> list[dict]:
    """Generate a regular tile grid covering ``moc_to_tile``. Pure computation, no DB access.

    Ports the prototype's ``GenerateSkyTiles``. Returns a list of plain dicts
    (name, ra, decl, delta_ra, delta_decl, footprint) — the API/CLI boundary
    wraps each into a ``TileCreate`` (encoding ``footprint`` as a depth-29
    range list) before this ever leaves the service layer. Inputs are arcmin
    (matching the CLI/API parameter names); ``delta_ra``/``delta_decl`` in the
    returned dicts (and the persisted ``Tile`` columns) are degrees, not
    arcmin — converted once here and never converted back.
    """
    orig_deg_height = tile_side_length_arc_min / 60.0
    orig_deg_width = tile_side_length_arc_min / 60.0
    deg_height = (tile_side_length_arc_min - overlap_in_arc_min) / 60.0
    deg_width = (tile_side_length_arc_min - overlap_in_arc_min) / 60.0

    # Avoids generating duplicate tiles at the 0/360 and +/-90 wrap boundaries.
    threshold = 0.1 / 3600.0
    northern_limit = 90.0 - threshold - deg_height
    southern_limit = -90.0
    eastern_limit = 360.0 - threshold - deg_width
    western_limit = 0.0

    dec_range = northern_limit - southern_limit
    ra_range = eastern_limit - western_limit

    frac_dec_tile, num_dec_tiles = math.modf(dec_range / deg_height)
    total_dec_tiles = int(num_dec_tiles) + 1
    if num_dec_tiles == 0:
        num_dec_tiles = 1
    dec_differential = (deg_height - (frac_dec_tile * deg_height)) / num_dec_tiles
    dec_delta = deg_height - dec_differential
    starting_dec = southern_limit + deg_height / 2.0

    decs = [starting_dec + i * dec_delta for i in range(total_dec_tiles)]

    ras_over_decs = []
    for d in decs:
        adjusted_tile_width = deg_width / np.abs(np.cos(np.radians(d)))
        frac_ra_tile, num_ra_tiles = math.modf(ra_range / adjusted_tile_width)
        total_ra_tiles = int(num_ra_tiles) + 1
        if num_ra_tiles == 0:
            num_ra_tiles = 1
        ra_differential = (
            adjusted_tile_width - (frac_ra_tile * adjusted_tile_width)
        ) / num_ra_tiles
        ra_delta = adjusted_tile_width - ra_differential
        starting_ra = adjusted_tile_width / 2.0
        ras_over_decs.append(
            [starting_ra + i * ra_delta for i in range(total_ra_tiles)]
        )

    ra_values: list[float] = []
    dec_values: list[float] = []
    for d, ras in zip(decs, ras_over_decs):
        for r in ras:
            ra_values.append(float(r))
            dec_values.append(float(d))

    all_sky_coords = SkyCoord(
        np.asarray(ra_values),
        np.asarray(dec_values),
        unit=(u.degree, u.degree),
        frame="icrs",
    )

    covered_area = moc_to_tile.sky_fraction * 41252.96
    bary = moc_to_tile.barycenter()
    fov_degrees = 2 * np.sqrt(covered_area)
    nearby_coords = all_sky_coords[all_sky_coords.separation(bary).degree <= fov_degrees]

    x_step = orig_deg_width / 2.0
    y_step = orig_deg_height / 2.0

    tiles = []
    tile_num = 1
    for coord in nearby_coords:
        x_step_adjusted = x_step / np.cos(np.radians(coord.dec.degree))
        corner_ras = np.asarray(
            [
                coord.ra.degree + x_step_adjusted,
                coord.ra.degree + x_step_adjusted,
                coord.ra.degree - x_step_adjusted,
                coord.ra.degree - x_step_adjusted,
            ]
        )
        corner_decs = np.asarray(
            [
                coord.dec.degree + y_step,
                coord.dec.degree - y_step,
                coord.dec.degree - y_step,
                coord.dec.degree + y_step,
            ]
        )
        corner_coords = SkyCoord(corner_ras, corner_decs, unit="deg", frame="icrs")
        tile_moc = MOC.from_polygon_skycoord(
            corner_coords, complement=False, max_depth=_TILE_FOOTPRINT_MAX_DEPTH
        )

        if moc_to_tile.intersection(tile_moc).sky_fraction > 0:
            tiles.append(
                {
                    "name": f"Tile_{tile_num}",
                    "ra": float(coord.ra.degree),
                    "decl": float(coord.dec.degree),
                    "delta_ra": float(deg_width),
                    "delta_decl": float(deg_height),
                    "footprint": tile_moc,
                }
            )
            tile_num += 1

    return tiles


def create_tiles(db: Session, project_id: int, tiles: list[dict]) -> list[Tile]:
    """Bulk-insert Tile rows and associate each with its overlapping Level2Calibrations.

    ``tiles`` are plain dicts already carrying real ``mocpy.MOC`` footprints
    (name, ra, decl, delta_ra, delta_decl, footprint) — the API/CLI boundary is
    responsible for decoding each ``TileCreate.footprint`` range list into a MOC
    via ``ranges_to_moc`` before calling this.
    """
    if not tiles:
        return []

    rows = [{**tile, "project_id": project_id} for tile in tiles]
    created = (
        db.execute(sa.insert(Tile).returning(Tile), rows).scalars().all()
    )
    db.flush()

    _associate_tiles_with_overlapping_calibrations(db, project_id, created)
    db.commit()
    return list(created)


def _associate_tiles_with_overlapping_calibrations(
    db: Session, project_id: int, tiles: Sequence[Tile]
) -> None:
    """Populate tile_level2_calibration_association for each tile's spatial overlap."""
    association_rows: list[dict] = []
    for tile in tiles:
        if tile.footprint is None:
            continue
        overlap_stmt = sa.select(Level2Calibration.id).where(
            Level2Calibration.project_id == project_id,
            Level2Calibration.footprint.isnot(None),
            Level2Calibration.footprint.op("&&")(
                sa.literal(tile.footprint, type_=MOCType)
            ),
        )
        association_rows.extend(
            {"tile_id": tile.id, "level2_calibration_id": cal_id}
            for (cal_id,) in db.execute(overlap_stmt).all()
        )

    if association_rows:
        db.execute(
            pg_insert(tile_level2_calibration_association)
            .values(association_rows)
            .on_conflict_do_nothing(
                index_elements=["tile_id", "level2_calibration_id"]
            )
        )


def tile_with_most_calibrations(db: Session, tile_ids: Sequence[int]) -> int | None:
    """Return whichever of ``tile_ids`` has the most associated Level2Calibrations, or None if all have zero.

    A regular tessellation grid over an arbitrary region routinely produces
    tiles with no real spatial overlap at all (edge cells, sparse coverage) —
    callers that need one "representative" tile (e.g. a demo/smoke run) must
    pick by actual data content, never by position in the list.
    """
    stmt = (
        sa.select(
            tile_level2_calibration_association.c.tile_id,
            sa.func.count().label("n"),
        )
        .where(tile_level2_calibration_association.c.tile_id.in_(tile_ids))
        .group_by(tile_level2_calibration_association.c.tile_id)
        .order_by(sa.desc("n"))
        .limit(1)
    )
    row = db.execute(stmt).first()
    return row.tile_id if row else None
