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


def test_get_statuses_returns_db_driven_values(client, mock_db):
    mock_db.execute.return_value.fetchall.return_value = [
        MagicMock(value="pending"),
        MagicMock(value="in_process"),
        MagicMock(value="complete"),
        MagicMock(value="failed"),
    ]

    response = client.get("/api/v1/meta/statuses")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 4
    assert [item["value"] for item in data] == [
        "pending",
        "in_process",
        "complete",
        "failed",
    ]
    assert data[1]["label"] == "In Process"
    assert data[2]["color"] == "#2e7d32"
    assert data[3]["color"] == "#c62828"
    mock_db.execute.assert_called_once()
