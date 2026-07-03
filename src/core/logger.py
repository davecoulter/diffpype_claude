"""Structured logging configuration for Diffpype.

All components stream JSON logs to stdout via ``structlog``. Correlation IDs are
threaded through ``structlog.contextvars`` so a single request or task can be
traced across the FastAPI, service, and Celery boundaries.
"""
import logging

import structlog


def configure_logging(level: int = logging.INFO) -> None:
    """Configure structlog to emit JSON to stdout with contextvar merging.

    Idempotent: safe to call from every entry point (FastAPI app, Celery app).
    """
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
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
