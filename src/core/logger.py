"""Structured logging configuration for Diffpype.

All components stream JSON logs to stdout via ``structlog``. The correlation ID is
sourced from the active OpenTelemetry trace, so a single request or task can be
traced across the FastAPI, service, and Celery boundaries without manual threading.
"""

import logging

import structlog
from opentelemetry import trace

from src.core.config import settings


def _add_trace_correlation_id(logger, method_name, event_dict):
    """Attach the active OTel trace ID (32-char hex) to each log event as correlation_id."""
    span_context = trace.get_current_span().get_span_context()
    if span_context.is_valid:
        event_dict.setdefault("correlation_id", format(span_context.trace_id, "032x"))
    return event_dict


def configure_logging(level: int | None = None) -> None:
    """Configure structlog to emit JSON to stdout with OTel trace correlation.

    Idempotent: safe to call from every entry point (FastAPI app, Celery app).
    The level defaults to ``settings.log_level`` (from the validated config).
    """
    if level is None:
        level = getattr(logging, settings.log_level.upper(), logging.INFO)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            _add_trace_correlation_id,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(*args, **kwargs) -> structlog.stdlib.BoundLogger:
    """Return a structlog logger bound to any active contextvars."""
    return structlog.get_logger(*args, **kwargs)
