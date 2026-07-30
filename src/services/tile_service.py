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

from src.db.enums import RegionSource
from src.db.models import Level2Calibration, Tile, tile_level2_calibration_association
from src.db.spatial_types import MOCType, union_mocs

# HEALPix order for generated tile footprints, matching the prototype's ported
# convention for tile-scale (not detector-scale) precision. MOCType normalizes
# any input depth to depth 29 on persistence, so this only affects computation.
_TILE_FOOTPRINT_MAX_DEPTH = 21

# HEALPix order for the resolved region MOC (cone/bounding-box/project-footprint),
# matching the CLI's existing cone precision (`_cone_moc` uses max_depth=10).
_REGION_MAX_DEPTH = 10


def generate_tile_tessellation(
    tile_side_length_arc_min: float,
    moc_to_tile: MOC,
    overlap_in_arc_min: float = 0.0,
    overlap_only: bool = True,
) -> list[dict]:
    """Generate a regular tile grid covering ``moc_to_tile``. Pure computation, no DB access.

    Ports the prototype's ``GenerateSkyTiles``. Returns a list of plain dicts
    (name, ra, decl, delta_ra, delta_decl, footprint) — the API/CLI boundary
    wraps each into a ``TileCreate`` (encoding ``footprint`` as a depth-29
    range list) before this ever leaves the service layer. Inputs are arcmin
    (matching the CLI/API parameter names); ``delta_ra``/``delta_decl`` in the
    returned dicts (and the persisted ``Tile`` columns) are degrees, not
    arcmin — converted once here and never converted back.

    ``overlap_only`` (default ``True``) keeps only tiles that actually intersect
    ``moc_to_tile``; ``False`` keeps the full rectangular grid regardless of
    intersection, to pre-provision tiles over a region ahead of incoming survey
    data.
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
    nearby_coords = all_sky_coords[
        all_sky_coords.separation(bary).degree <= fov_degrees
    ]

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

        if not overlap_only or moc_to_tile.intersection(tile_moc).sky_fraction > 0:
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


def _resolve_region_moc(
    db: Session,
    region_source: RegionSource,
    *,
    ra: float | None = None,
    decl: float | None = None,
    radius_deg: float | None = None,
    project_id: int | None = None,
    min_ra: float | None = None,
    max_ra: float | None = None,
    min_decl: float | None = None,
    max_decl: float | None = None,
) -> MOC:
    """Convert a ``region_source`` and its mode-specific parameters into a single MOC.

    ``cone`` and ``bounding_box`` are pure geometry; ``project_footprint`` queries
    every ``Level2Calibration`` footprint under ``project_id`` and unions them via
    ``union_mocs``. Raises ``ValueError`` if the fields required by ``region_source``
    are missing, or if a ``project_footprint`` request names a project with no
    footprints to derive a region from. (The API boundary validates required fields
    up front via Pydantic; this guard gives the CLI boundary the same protection.)
    """

    def _require(**fields: object) -> None:
        missing = [name for name, value in fields.items() if value is None]
        if missing:
            raise ValueError(
                f"region_source={region_source.value} requires: {', '.join(missing)}"
            )

    if region_source == RegionSource.CONE:
        _require(ra=ra, decl=decl, radius_deg=radius_deg)
        return MOC.from_cone(
            lon=ra * u.deg,
            lat=decl * u.deg,
            radius=radius_deg * u.deg,
            max_depth=_REGION_MAX_DEPTH,
        )
    if region_source == RegionSource.BOUNDING_BOX:
        _require(min_ra=min_ra, max_ra=max_ra, min_decl=min_decl, max_decl=max_decl)
        corners = SkyCoord(
            [min_ra, max_ra, max_ra, min_ra],
            [min_decl, min_decl, max_decl, max_decl],
            unit="deg",
            frame="icrs",
        )
        return MOC.from_polygon_skycoord(
            corners, complement=False, max_depth=_REGION_MAX_DEPTH
        )

    _require(project_id=project_id)
    footprints = [
        row[0]
        for row in db.execute(
            sa.select(Level2Calibration.footprint).where(
                Level2Calibration.project_id == project_id,
                Level2Calibration.footprint.isnot(None),
            )
        ).all()
    ]
    if not footprints:
        raise ValueError(
            "project_footprint tessellation requires at least one calibration with "
            f"a footprint under project_id={project_id}"
        )
    return union_mocs(footprints)


def generate_tessellation_for_region(
    db: Session,
    region_source: RegionSource,
    tile_side_length_arc_min: float,
    overlap_in_arc_min: float = 0.0,
    overlap_only: bool = True,
    *,
    ra: float | None = None,
    decl: float | None = None,
    radius_deg: float | None = None,
    project_id: int | None = None,
    min_ra: float | None = None,
    max_ra: float | None = None,
    min_decl: float | None = None,
    max_decl: float | None = None,
) -> list[dict]:
    """Resolve a ``region_source`` into a MOC, then generate its tile tessellation.

    The single service entry point both the API route and CLI delegate to, keeping
    the pure ``generate_tile_tessellation`` free of DB access while supporting all
    three region modes.
    """
    moc_to_tile = _resolve_region_moc(
        db,
        region_source,
        ra=ra,
        decl=decl,
        radius_deg=radius_deg,
        project_id=project_id,
        min_ra=min_ra,
        max_ra=max_ra,
        min_decl=min_decl,
        max_decl=max_decl,
    )
    return generate_tile_tessellation(
        tile_side_length_arc_min, moc_to_tile, overlap_in_arc_min, overlap_only
    )


def create_tiles(db: Session, project_id: int, tiles: list[dict]) -> list[Tile]:
    """Bulk-insert Tile rows and associate each with its overlapping Level2Calibrations.

    ``tiles`` are plain dicts already carrying real ``mocpy.MOC`` footprints
    (name, ra, decl, delta_ra, delta_decl, footprint) — the API/CLI boundary is
    responsible for decoding each ``TileCreate.footprint`` range list into a MOC
    via ``ranges_to_moc`` before calling this.
    """
    if not tiles:
        return []

    # healpix_index is derived from ra/decl (PointHEALPixType computes the depth-29
    # cell from the tuple); Tile.healpix_index is NOT NULL, so every row must carry it.
    rows = [
        {
            **tile,
            "project_id": project_id,
            "healpix_index": (tile["ra"], tile["decl"]),
        }
        for tile in tiles
    ]
    created = db.execute(sa.insert(Tile).returning(Tile), rows).scalars().all()
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
            .on_conflict_do_nothing(index_elements=["tile_id", "level2_calibration_id"])
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
