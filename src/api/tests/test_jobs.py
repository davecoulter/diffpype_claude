from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from src.api.main import app
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


def test_reconcile_returns_failed_entities(client, mock_db, mocker):
    mocker.patch(
        "src.services.job_service.reconcile_stuck_jobs",
        return_value=[{"entity": "IngestBatch", "id": 1, "age_seconds": 9000.0}],
    )

    response = client.post("/api/v1/jobs/reconcile", json={"threshold_seconds": 3600})

    assert response.status_code == 200
    assert response.json()["reconciled"][0]["id"] == 1


def test_reconcile_uses_default_threshold_when_omitted(client, mock_db, mocker):
    reconcile = mocker.patch(
        "src.services.job_service.reconcile_stuck_jobs", return_value=[]
    )

    response = client.post("/api/v1/jobs/reconcile", json={})

    assert response.status_code == 200
    assert response.json() == {"reconciled": []}
    # Called with the session only (no explicit threshold => service default).
    assert reconcile.call_args[0][1:] == ()


def test_reconcile_invalid_threshold_type_is_422(client, mock_db):
    response = client.post(
        "/api/v1/jobs/reconcile", json={"threshold_seconds": "not-an-int"}
    )
    assert response.status_code == 422
