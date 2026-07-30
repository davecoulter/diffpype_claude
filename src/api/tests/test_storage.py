import pytest
from fastapi.testclient import TestClient

from src.api.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_storage_sync_dispatches_and_returns_job_id(client, mocker):
    mocker.patch(
        "src.services.storage_service.dispatch_staging_sync", return_value="job-99"
    )

    response = client.post(
        "/api/v1/storage/sync",
        json={"staging_location": "/staging", "canonical_prefix": "raw"},
    )

    assert response.status_code == 200
    assert response.json() == {"job_id": "job-99"}


def test_storage_sync_defaults_canonical_prefix_to_empty(client, mocker):
    dispatch = mocker.patch(
        "src.services.storage_service.dispatch_staging_sync", return_value="job-1"
    )

    response = client.post(
        "/api/v1/storage/sync", json={"staging_location": "/staging"}
    )

    assert response.status_code == 200
    dispatch.assert_called_once_with("/staging", "")


def test_storage_sync_missing_staging_location_is_422(client):
    response = client.post("/api/v1/storage/sync", json={"canonical_prefix": "raw"})
    assert response.status_code == 422
