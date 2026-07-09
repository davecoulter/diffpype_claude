"""OpenTelemetry initialization: tracer provider, OTLP exporter, and instrumentation.

This module owns all OTel setup so the FastAPI app, the SQLAlchemy engine, and the
Celery worker are traced through a single, idempotent entry point. The OTLP exporter
reads ``OTEL_EXPORTER_OTLP_ENDPOINT`` natively per the OTel specification; it is only
attached when that variable is present, so unit tests and local runs create spans
without a live collector.
"""
import os

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.celery import CeleryInstrumentor
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from src.core.logger import get_logger

_configured = False
_app_instrumented = False


def setup_tracing(app=None, engine=None) -> None:
    """Configure the global tracer provider and instrument FastAPI, SQLAlchemy, and Celery once.

    Safe to call from multiple entry points in one process: the provider and the
    global SQLAlchemy/Celery instrumentors are installed once, and the FastAPI app
    is instrumented once, regardless of call order.
    """
    global _configured, _app_instrumented

    if not _configured:
        provider = TracerProvider()
        endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
        if endpoint:
            provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
        trace.set_tracer_provider(provider)
        SQLAlchemyInstrumentor().instrument(engine=engine)
        CeleryInstrumentor().instrument()
        _configured = True

        if endpoint:
            get_logger().info("tracing_configured", exporter_endpoint=endpoint)
        else:
            # Spans are still created and locally observable, but nothing leaves the
            # process — surface this so a misconfigured prod env is not silent.
            get_logger().warning(
                "tracing_configured_without_exporter",
                detail="OTEL_EXPORTER_OTLP_ENDPOINT unset; spans created but not exported",
            )

    if app is not None and not _app_instrumented:
        FastAPIInstrumentor.instrument_app(app)
        _app_instrumented = True
