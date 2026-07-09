from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.db.models import DummyImage
from src.db.session import get_db

VALID_PAYLOAD = {"task_name": "dummy_sleep", "config": {"sleep_duration": 5}}


@pytest.fixture
def mock_db():
    db = MagicMock()
    app.dependency_overrides[get_db] = lambda: db
    yield db
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def client():
    return TestClient(app)


def test_create_dummy_job_delegates_to_service_and_returns_ids(client, mock_db, mocker):
    mocker.patch(
        "src.services.job_service.dispatch_dummy_job",
        return_value=("fake-task-id", 1),
    )

    response = client.post("/api/v1/jobs/dummy", json=VALID_PAYLOAD)

    assert response.status_code == 200
    assert response.json() == {"job_id": "fake-task-id", "image_id": 1}


def test_create_dummy_job_rejects_sleep_duration_above_max(client):
    response = client.post(
        "/api/v1/jobs/dummy",
        json={"task_name": "dummy_sleep", "config": {"sleep_duration": 11}},
    )
    assert response.status_code == 422


def test_create_dummy_job_rejects_sleep_duration_below_min(client):
    response = client.post(
        "/api/v1/jobs/dummy",
        json={"task_name": "dummy_sleep", "config": {"sleep_duration": 0}},
    )
    assert response.status_code == 422


def test_get_dummy_job_status_returns_image(client, mock_db, mocker):
    mocker.patch(
        "src.services.job_service.get_dummy_job",
        return_value=DummyImage(id=5, status="complete", latest_job_id="task-123"),
    )

    response = client.get("/api/v1/jobs/dummy/5")

    assert response.status_code == 200
    assert response.json() == {
        "id": 5,
        "status": "complete",
        "latest_job_id": "task-123",
        "created_at": None,
        "job_started_at": None,
        "job_finished_at": None,
    }


def test_get_dummy_job_status_404_when_missing(client, mock_db, mocker):
    mocker.patch("src.services.job_service.get_dummy_job", return_value=None)

    response = client.get("/api/v1/jobs/dummy/999")

    assert response.status_code == 404
