from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.db.enums import JobStatus
from src.db.models import IngestBatch
from src.db.session import get_db


@pytest.fixture
def mock_db():
    db = MagicMock()
    app.dependency_overrides[get_db] = lambda: db
    yield db
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def client():
    return TestClient(app)


def test_create_ingest_batch_returns_job_and_batch_id(client, mock_db, mocker):
    mocker.patch(
        "src.services.ingest_service.create_ingest_batch",
        return_value=("fake-task-id", 7),
    )

    response = client.post(
        "/api/v1/ingest", json={"project_id": 1, "s3_prefix": "raw/"}
    )

    assert response.status_code == 200
    assert response.json() == {"job_id": "fake-task-id", "batch_id": 7}


def test_get_ingest_batch_status_returns_batch(client, mock_db, mocker):
    mocker.patch(
        "src.services.ingest_service.get_ingest_batch",
        return_value=IngestBatch(
            id=7,
            project_id=1,
            s3_prefix="raw/",
            total_files=10,
            processed_files=10,
            status=JobStatus.COMPLETE,
        ),
    )

    response = client.get("/api/v1/ingest/7")

    assert response.status_code == 200
    assert response.json() == {
        "id": 7,
        "project_id": 1,
        "s3_prefix": "raw/",
        "total_files": 10,
        "processed_files": 10,
        "status": "complete",
    }


def test_get_ingest_batch_status_404_when_missing(client, mock_db, mocker):
    mocker.patch(
        "src.services.ingest_service.get_ingest_batch", return_value=None
    )

    response = client.get("/api/v1/ingest/999")

    assert response.status_code == 404
