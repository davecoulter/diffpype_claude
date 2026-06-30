from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.db.models import DummyImage
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


def test_create_dummy_job_dispatches_task_and_returns_ids(client, mock_db, mocker):
    def fake_refresh(image):
        image.id = 1

    mock_db.refresh.side_effect = fake_refresh

    fake_async_result = MagicMock(id="fake-task-id")
    mock_delay = mocker.patch(
        "src.api.main.sleep_and_update_status.delay", return_value=fake_async_result
    )

    response = client.post("/jobs/dummy")

    assert response.status_code == 200
    assert response.json() == {"job_id": "fake-task-id", "image_id": 1}
    mock_db.add.assert_called_once()
    assert mock_db.commit.call_count == 2
    mock_delay.assert_called_once_with(1)


def test_get_dummy_job_status_returns_image(client, mock_db):
    mock_db.get.return_value = DummyImage(id=5, status="Success", latest_job_id="task-123")

    response = client.get("/jobs/dummy/5")

    assert response.status_code == 200
    assert response.json() == {"id": 5, "status": "Success", "latest_job_id": "task-123"}


def test_get_dummy_job_status_404_when_missing(client, mock_db):
    mock_db.get.return_value = None

    response = client.get("/jobs/dummy/999")

    assert response.status_code == 404
