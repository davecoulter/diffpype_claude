"""Unit tests for API schema models."""

import astropy.units as u
import pytest
from mocpy import MOC
from pydantic import ValidationError

from src.api.schemas import PaginationParams, TileRead
from src.db.spatial_types import moc_to_ranges


def test_pagination_params_defaults():
    """PaginationParams must default to limit=100 and offset=0."""
    p = PaginationParams()
    assert p.limit == 100
    assert p.offset == 0


def test_pagination_params_valid_boundaries():
    """Boundary values limit=1, limit=1000, and offset=0 must be accepted."""
    assert PaginationParams(limit=1, offset=0).limit == 1
    assert PaginationParams(limit=1000, offset=0).limit == 1000


def test_pagination_params_limit_zero_rejected():
    """limit=0 must raise ValidationError (ge=1)."""
    with pytest.raises(ValidationError):
        PaginationParams(limit=0)


def test_pagination_params_limit_above_max_rejected():
    """limit=1001 must raise ValidationError (le=1000)."""
    with pytest.raises(ValidationError):
        PaginationParams(limit=1001)


def test_pagination_params_negative_offset_rejected():
    """offset=-1 must raise ValidationError (ge=0)."""
    with pytest.raises(ValidationError):
        PaginationParams(offset=-1)


def test_tile_read_coerces_a_real_moc_footprint_to_a_range_list():
    """model_validate against an ORM-shaped object with a real mocpy.MOC footprint attribute."""
    moc = MOC.from_cone(
        lon=10 * u.deg, lat=20 * u.deg, radius=0.1 * u.deg, max_depth=10
    )

    class _FakeTile:
        id = 1
        name = "Tile_1"
        ra = 10.0
        decl = 20.0
        delta_ra = 0.2
        delta_decl = 0.2
        footprint = moc
        project_id = 1

    result = TileRead.model_validate(_FakeTile(), from_attributes=True)

    assert result.footprint == moc_to_ranges(moc)
