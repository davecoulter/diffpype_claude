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
def tessellate_tiles(body: TileTessellationRequest) -> list[TileCreate]:
    moc_to_tile = ranges_to_moc(body.moc_to_tile)
    tiles = tile_service.generate_tile_tessellation(
        body.tile_side_length_arc_min, moc_to_tile, body.overlap_in_arc_min
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
