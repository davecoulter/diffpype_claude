"""Unit tests for the structlog trace-correlation processor."""
from unittest.mock import MagicMock

from src.core.logger import _add_trace_correlation_id


def test_add_trace_correlation_id_sets_hex_id_for_valid_span(mocker):
    """A valid active span injects its trace ID as a 32-char hex correlation_id."""
    span = MagicMock()
    span.get_span_context.return_value = MagicMock(is_valid=True, trace_id=0x1234ABCD)
    mocker.patch("src.core.logger.trace.get_current_span", return_value=span)

    result = _add_trace_correlation_id(None, "info", {})

    assert result["correlation_id"] == format(0x1234ABCD, "032x")


def test_add_trace_correlation_id_noops_without_valid_span(mocker):
    """With no valid span, the event dict is returned untouched."""
    span = MagicMock()
    span.get_span_context.return_value = MagicMock(is_valid=False)
    mocker.patch("src.core.logger.trace.get_current_span", return_value=span)

    result = _add_trace_correlation_id(None, "info", {"event": "x"})

    assert "correlation_id" not in result


def test_add_trace_correlation_id_does_not_overwrite_existing(mocker):
    """An explicitly bound correlation_id must win over the derived trace ID."""
    span = MagicMock()
    span.get_span_context.return_value = MagicMock(is_valid=True, trace_id=0x1)
    mocker.patch("src.core.logger.trace.get_current_span", return_value=span)

    result = _add_trace_correlation_id(None, "info", {"correlation_id": "preset"})

    assert result["correlation_id"] == "preset"
