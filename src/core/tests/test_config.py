"""Unit tests for the Settings configuration class."""
import pytest
from pydantic import ValidationError

from src.core.config import Settings


def test_db_pool_size_parses_from_env(monkeypatch):
    """Settings must read DB_POOL_SIZE from the environment as an integer."""
    monkeypatch.setenv("DB_POOL_SIZE", "5")
    assert Settings().db_pool_size == 5


def test_db_max_overflow_parses_from_env(monkeypatch):
    """Settings must read DB_MAX_OVERFLOW from the environment as an integer."""
    monkeypatch.setenv("DB_MAX_OVERFLOW", "3")
    assert Settings().db_max_overflow == 3


def test_db_pool_size_default():
    """db_pool_size defaults to 20 when DB_POOL_SIZE is not overridden."""
    assert Settings().db_pool_size == 20


def test_db_max_overflow_default():
    """db_max_overflow defaults to 10 when DB_MAX_OVERFLOW is not overridden."""
    assert Settings().db_max_overflow == 10


def test_db_pool_size_rejects_non_integer(monkeypatch):
    """Settings must raise ValidationError for a non-integer DB_POOL_SIZE."""
    monkeypatch.setenv("DB_POOL_SIZE", "not_a_number")
    with pytest.raises(ValidationError):
        Settings()
