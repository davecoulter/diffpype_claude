from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from src.api.main import app, sqladmin_exception_handler
from src.core.logger import get_logger

# A real, mutating POST endpoint used to exercise cross-cutting middleware
# (correlation-id header, OTel tracing, metrics, the 500 handler, CORS). The
# Stage-0 /jobs/dummy endpoint that previously served this role was removed with
# the DummyImage decommission (doc 29); project creation is its replacement.
VALID_PAYLOAD = {"name": "Test Project", "description": None, "user_id": 1}


def _mock_create_project(mocker, **overrides):
    """Patch project_service.create_project to return a Project-like object."""
    project = SimpleNamespace(
        id=1,
        name="Test Project",
        slug="test-project",
        description=None,
        user_id=1,
    )
    kwargs = {"return_value": project}
    kwargs.update(overrides)
    return mocker.patch(
        "src.api.routes.projects.project_service.create_project", **kwargs
    )


def test_correlation_id_header_is_a_32_char_hex_trace_id(mocker):
    _mock_create_project(mocker)
    client = TestClient(app)

    response = client.post("/api/v1/projects", json=VALID_PAYLOAD)

    assert response.status_code == 200
    correlation_id = response.headers["X-Correlation-ID"]
    assert len(correlation_id) == 32
    int(correlation_id, 16)  # raises ValueError if not valid hex


def test_correlation_id_header_matches_active_otel_trace_id(mocker):
    """The X-Correlation-ID header must equal the trace ID of the request's span."""
    from opentelemetry import trace
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    _mock_create_project(mocker)
    # main.py sets the global provider at import; attach an in-memory exporter to it
    # (the OTel global provider is a write-once singleton, so we cannot swap in a
    # fresh one here — we capture spans from the provider the app already uses).
    exporter = InMemorySpanExporter()
    trace.get_tracer_provider().add_span_processor(SimpleSpanProcessor(exporter))

    client = TestClient(app)
    response = client.post("/api/v1/projects", json=VALID_PAYLOAD)

    assert response.status_code == 200
    spans = exporter.get_finished_spans()
    assert spans, "expected the instrumented app to export at least one span"
    trace_id_hex = format(spans[0].context.trace_id, "032x")
    assert response.headers["X-Correlation-ID"] == trace_id_hex


def test_metrics_endpoint_exposes_prometheus_text(mocker):
    _mock_create_project(mocker)
    client = TestClient(app)
    client.post("/api/v1/projects", json=VALID_PAYLOAD)  # record one sample

    response = client.get("/metrics")

    assert response.status_code == 200
    assert "starlette_requests" in response.text


def test_sqladmin_exception_handler_logs_and_reraises(mocker):
    """The sqladmin sub-app handler must log the failure and re-raise the exception."""
    from unittest.mock import MagicMock

    mock_log = MagicMock()
    mocker.patch("src.api.main.get_logger", return_value=mock_log)
    exc = RuntimeError("admin boom")

    with pytest.raises(RuntimeError, match="admin boom"):
        sqladmin_exception_handler(MagicMock(), exc)

    mock_log.error.assert_called_once_with("sqladmin_unhandled_exception", exc_info=exc)


def test_unhandled_exception_returns_500(mocker):
    _mock_create_project(mocker, side_effect=RuntimeError("kaboom"))
    client = TestClient(app, raise_server_exceptions=False)

    response = client.post("/api/v1/projects", json=VALID_PAYLOAD)

    assert response.status_code == 500
    assert response.json() == {"detail": "Internal Server Error"}


def test_get_logger_returns_usable_logger():
    log = get_logger("test")
    # bind returns a logger; calling a level method must not raise.
    log.info("smoke_test", key="value")


def test_admin_unauthenticated_redirects_to_login():
    client = TestClient(app, follow_redirects=False)
    response = client.get("/admin/")
    assert response.status_code == 302
    assert "/admin/login" in response.headers["location"]


def test_old_unversioned_projects_path_returns_404():
    """Old unversioned routes must 404 after the /api/v1 prefix was introduced."""
    client = TestClient(app)
    assert client.post("/projects", json=VALID_PAYLOAD).status_code == 404


def test_old_unversioned_meta_path_returns_404():
    """Old /meta/... routes must 404 after the /api/v1 prefix was introduced."""
    client = TestClient(app)
    assert client.get("/meta/statuses").status_code == 404


def test_cors_rejects_disallowed_origin(mocker):
    _mock_create_project(mocker)
    client = TestClient(app)
    response = client.post(
        "/api/v1/projects",
        json=VALID_PAYLOAD,
        headers={"Origin": "http://evil.example.com"},
    )
    assert "access-control-allow-origin" not in response.headers
