from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.db.models import Project
from src.db.session import get_db

VALID_PAYLOAD = {"name": "My Survey", "description": "desc", "user_id": 1}


@pytest.fixture
def mock_db():
    db = MagicMock()
    app.dependency_overrides[get_db] = lambda: db
    yield db
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def client():
    return TestClient(app)


def test_create_project_returns_created_project(client, mock_db, mocker):
    mocker.patch(
        "src.services.project_service.create_project",
        return_value=Project(
            id=1, name="My Survey", slug="my-survey", description="desc", user_id=1
        ),
    )

    response = client.post("/api/v1/projects", json=VALID_PAYLOAD)

    assert response.status_code == 200
    assert response.json() == {
        "id": 1,
        "name": "My Survey",
        "slug": "my-survey",
        "description": "desc",
        "user_id": 1,
    }


def test_create_project_returns_400_on_slug_collision(client, mock_db, mocker):
    mocker.patch(
        "src.services.project_service.create_project",
        side_effect=ValueError("A project with slug 'my-survey' already exists"),
    )

    response = client.post("/api/v1/projects", json=VALID_PAYLOAD)

    assert response.status_code == 400
    assert "already exists" in response.json()["detail"]
