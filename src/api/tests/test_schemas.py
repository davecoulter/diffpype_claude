"""Unit tests for API schema models."""
import pytest
from pydantic import ValidationError

from src.api.schemas import PaginationParams


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
