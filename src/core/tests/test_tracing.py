"""Unit tests for OpenTelemetry setup in src.core.tracing."""

from unittest.mock import MagicMock

import src.core.tracing as tracing


def _reset_flags(monkeypatch):
    """Force setup_tracing to run its full configuration path on the next call."""
    monkeypatch.setattr(tracing, "_configured", False)
    monkeypatch.setattr(tracing, "_app_instrumented", False)


def test_setup_tracing_configures_provider_and_instruments(mocker, monkeypatch):
    """With an OTLP endpoint set, the exporter, instrumentors, and app are all wired."""
    _reset_flags(monkeypatch)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://jaeger:4317")

    mock_provider = MagicMock()
    mocker.patch.object(tracing, "TracerProvider", return_value=mock_provider)
    mock_batch = mocker.patch.object(tracing, "BatchSpanProcessor")
    mocker.patch.object(tracing, "OTLPSpanExporter")
    mock_set_provider = mocker.patch.object(tracing.trace, "set_tracer_provider")
    mock_sa = mocker.patch.object(tracing, "SQLAlchemyInstrumentor")
    mock_celery = mocker.patch.object(tracing, "CeleryInstrumentor")
    mock_fastapi = mocker.patch.object(tracing, "FastAPIInstrumentor")
    mock_log = MagicMock()
    mocker.patch.object(tracing, "get_logger", return_value=mock_log)

    app = MagicMock()
    engine = MagicMock()
    tracing.setup_tracing(app=app, engine=engine)

    mock_provider.add_span_processor.assert_called_once_with(mock_batch.return_value)
    mock_set_provider.assert_called_once_with(mock_provider)
    mock_sa.return_value.instrument.assert_called_once_with(engine=engine)
    mock_celery.return_value.instrument.assert_called_once()
    mock_fastapi.instrument_app.assert_called_once_with(app)
    mock_log.info.assert_called_once()
    mock_log.warning.assert_not_called()


def test_setup_tracing_skips_exporter_without_endpoint(mocker, monkeypatch):
    """With no OTLP endpoint, no span processor is attached but instrumentation still runs."""
    _reset_flags(monkeypatch)
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)

    mock_provider = MagicMock()
    mocker.patch.object(tracing, "TracerProvider", return_value=mock_provider)
    mocker.patch.object(tracing.trace, "set_tracer_provider")
    mocker.patch.object(tracing, "SQLAlchemyInstrumentor")
    mocker.patch.object(tracing, "CeleryInstrumentor")
    mocker.patch.object(tracing, "FastAPIInstrumentor")
    mock_log = MagicMock()
    mocker.patch.object(tracing, "get_logger", return_value=mock_log)

    tracing.setup_tracing(engine=MagicMock())

    mock_provider.add_span_processor.assert_not_called()
    mock_log.warning.assert_called_once()
    mock_log.info.assert_not_called()


def test_setup_tracing_is_idempotent(mocker, monkeypatch):
    """A second call must not reconfigure the provider or re-instrument the app."""
    monkeypatch.setattr(tracing, "_configured", True)
    monkeypatch.setattr(tracing, "_app_instrumented", True)

    mock_provider_cls = mocker.patch.object(tracing, "TracerProvider")
    mock_fastapi = mocker.patch.object(tracing, "FastAPIInstrumentor")

    tracing.setup_tracing(app=MagicMock(), engine=MagicMock())

    mock_provider_cls.assert_not_called()
    mock_fastapi.instrument_app.assert_not_called()
