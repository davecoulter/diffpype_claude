from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.api.schemas import (
    TileBulkCreateRequest,
    TileCreate,
    TileRead,
    TileTessellationRequest,
)
from src.db.session import get_db
from src.db.spatial_types import moc_to_ranges, ranges_to_moc
from src.services import tile_service

router = APIRouter(prefix="/tiles", tags=["tiles"])


@router.post("/tessellate", response_model=list[TileCreate])
def tessellate_tiles(
    body: TileTessellationRequest, db: Session = Depends(get_db)
) -> list[TileCreate]:
    tiles = tile_service.generate_tessellation_for_region(
        db,
        body.region_source,
        body.tile_side_length_arc_min,
        body.overlap_in_arc_min,
        body.overlap_only,
        ra=body.ra,
        decl=body.decl,
        radius_deg=body.radius_deg,
        project_id=body.project_id,
        min_ra=body.min_ra,
        max_ra=body.max_ra,
        min_decl=body.min_decl,
        max_decl=body.max_decl,
    )
    return [
        TileCreate(
            name=t["name"],
            ra=t["ra"],
            decl=t["decl"],
            delta_ra=t["delta_ra"],
            delta_decl=t["delta_decl"],
            footprint=moc_to_ranges(t["footprint"]),
        )
        for t in tiles
    ]


@router.post("", response_model=list[TileRead])
def create_tiles(
    body: TileBulkCreateRequest, db: Session = Depends(get_db)
) -> list[TileRead]:
    tile_dicts = [
        {
            "name": t.name,
            "ra": t.ra,
            "decl": t.decl,
            "delta_ra": t.delta_ra,
            "delta_decl": t.delta_decl,
            "footprint": ranges_to_moc(t.footprint),
        }
        for t in body.tiles
    ]
    created = tile_service.create_tiles(db, body.project_id, tile_dicts)
    return [TileRead.model_validate(t) for t in created]
