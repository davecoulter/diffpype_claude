import uuid

from fastapi.testclient import TestClient

from src.api.main import app
from src.core.logger import get_logger

VALID_PAYLOAD = {"task_name": "dummy_sleep", "config": {"sleep_duration": 5}}


def test_correlation_id_header_is_present_and_valid_uuid(mocker):
    mocker.patch(
        "src.services.job_service.dispatch_dummy_job",
        return_value=("job-1", 1),
    )
    client = TestClient(app)

    response = client.post("/api/v1/jobs/dummy", json=VALID_PAYLOAD)

    assert response.status_code == 200
    correlation_id = response.headers["X-Correlation-ID"]
    # Raises ValueError if not a valid UUID.
    uuid.UUID(correlation_id)


def test_unhandled_exception_returns_500(mocker):
    mocker.patch(
        "src.services.job_service.dispatch_dummy_job",
        side_effect=RuntimeError("kaboom"),
    )
    client = TestClient(app, raise_server_exceptions=False)

    response = client.post("/api/v1/jobs/dummy", json=VALID_PAYLOAD)

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


def test_old_unversioned_jobs_path_returns_404():
    """Old /jobs/... routes must 404 after the /api/v1 prefix was introduced."""
    client = TestClient(app)
    assert client.post("/jobs/dummy", json=VALID_PAYLOAD).status_code == 404
    assert client.get("/jobs/dummy/1").status_code == 404


def test_old_unversioned_meta_path_returns_404():
    """Old /meta/... routes must 404 after the /api/v1 prefix was introduced."""
    client = TestClient(app)
    assert client.get("/meta/statuses").status_code == 404


def test_cors_rejects_disallowed_origin(mocker):
    mocker.patch(
        "src.services.job_service.dispatch_dummy_job",
        return_value=("job-1", 1),
    )
    client = TestClient(app)
    response = client.post(
        "/api/v1/jobs/dummy",
        json=VALID_PAYLOAD,
        headers={"Origin": "http://evil.example.com"},
    )
    assert "access-control-allow-origin" not in response.headers
