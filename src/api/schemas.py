from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from src.db.enums import JobStatus
from src.db.spatial_types import moc_to_ranges


class StatusMetadata(BaseModel):
    value: str
    label: str
    color: str


class PaginationParams(BaseModel):
    """Standard pagination controls for list endpoints; enforces safe upper bounds."""

    limit: int = Field(default=100, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)


class ProjectCreate(BaseModel):
    """Request body for creating a Project; its slug is derived from name server-side."""

    name: str
    description: str | None = None
    user_id: int


class ProjectRead(BaseModel):
    id: int
    name: str
    slug: str
    description: str | None
    user_id: int

    model_config = {"from_attributes": True}


class IngestRequest(BaseModel):
    """Request body dispatching an async ingest run over a storage prefix."""

    project_id: int
    s3_prefix: str


class IngestDispatchResponse(BaseModel):
    job_id: str
    batch_id: int


class IngestBatchStatus(BaseModel):
    id: int
    project_id: int
    s3_prefix: str
    total_files: int
    processed_files: int
    status: JobStatus

    model_config = {"from_attributes": True}


def _coerce_moc_footprint(value):
    """Convert a mocpy.MOC ORM attribute into its wire-safe depth-29 range list."""
    from mocpy import MOC

    if isinstance(value, MOC):
        return moc_to_ranges(value)
    return value


class TileCreate(BaseModel):
    name: str
    ra: float
    decl: float
    delta_ra: float  # degrees, not arcmin — see Tile.delta_ra
    delta_decl: float  # degrees, not arcmin — see Tile.delta_decl
    footprint: list[tuple[int, int]] | None = None

    _coerce_footprint = field_validator("footprint", mode="before")(
        _coerce_moc_footprint
    )


class EpochCreate(BaseModel):
    start_date: datetime
    end_date: datetime
    start_mjd: float
    end_mjd: float
    tile_id: int
    band_id: int


class EpochClusterRequest(BaseModel):
    """Request body for a no-write MJD-clustering preview over a tile+band."""

    project_id: int
    tile_id: int
    band_id: int
    peak_distance_thresh: float


class EpochBulkCreateRequest(BaseModel):
    project_id: int
    epochs: list[EpochCreate]


class MosaicCreate(BaseModel):
    """Request body creating a Level3Mosaic job-metadata row and dispatching its drizzle task."""

    project_id: int
    tile_id: int
    epoch_id: int
    band_id: int
    instrument_id: int
    filename: str
    target_plate_scale: float


class MosaicDispatchResponse(BaseModel):
    job_id: str
    mosaic_id: int


class MosaicStatus(BaseModel):
    id: int
    filename: str
    target_plate_scale: float
    ra: float | None
    decl: float | None
    status: JobStatus
    project_id: int
    tile_id: int
    epoch_id: int
    band_id: int
    instrument_id: int

    model_config = {"from_attributes": True}


class EpochRead(BaseModel):
    id: int
    start_date: datetime
    end_date: datetime
    start_mjd: float | None
    end_mjd: float | None
    project_id: int
    tile_id: int
    band_id: int

    model_config = {"from_attributes": True}


class TileTessellationRequest(BaseModel):
    """Request body for a no-DB tile-tessellation preview over a target region."""

    project_id: int
    tile_side_length_arc_min: float
    moc_to_tile: list[tuple[int, int]]
    overlap_in_arc_min: float = 0.0


class TileBulkCreateRequest(BaseModel):
    project_id: int
    tiles: list[TileCreate]


class TileRead(BaseModel):
    id: int
    name: str
    ra: float
    decl: float
    delta_ra: float
    delta_decl: float
    footprint: list[tuple[int, int]] | None
    project_id: int

    model_config = {"from_attributes": True}

    _coerce_footprint = field_validator("footprint", mode="before")(
        _coerce_moc_footprint
    )
