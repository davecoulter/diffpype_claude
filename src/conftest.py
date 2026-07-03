import pytest
from structlog.contextvars import clear_contextvars


@pytest.fixture(autouse=True)
def _clear_structlog_contextvars():
    """Isolate each test from any correlation_id bound by another test."""
    clear_contextvars()
    yield
    clear_contextvars()
