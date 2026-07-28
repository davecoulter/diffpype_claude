from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.db.models import Epoch
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


def test_cluster_epochs_returns_preview_without_writing(client, mock_db, mocker):
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = datetime(2024, 1, 2, tzinfo=timezone.utc)
    mocker.patch(
        "src.services.epoch_service.cluster_epochs",
        return_value=[
            {
                "start_date": start,
                "end_date": end,
                "start_mjd": 60300.0,
                "end_mjd": 60301.0,
                "tile_id": 1,
                "band_id": 2,
            }
        ],
    )

    response = client.post(
        "/api/v1/epochs/cluster",
        json={
            "project_id": 1,
            "tile_id": 1,
            "band_id": 2,
            "peak_distance_thresh": 5.0,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["start_mjd"] == 60300.0
    assert body[0]["tile_id"] == 1


def test_create_epochs_returns_persisted_epochs(client, mock_db, mocker):
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = datetime(2024, 1, 2, tzinfo=timezone.utc)
    mocker.patch(
        "src.services.epoch_service.create_epochs",
        return_value=[
            Epoch(
                id=1,
                start_date=start,
                end_date=end,
                start_mjd=60300.0,
                end_mjd=60301.0,
                project_id=1,
                tile_id=1,
                band_id=2,
            )
        ],
    )

    response = client.post(
        "/api/v1/epochs",
        json={
            "project_id": 1,
            "epochs": [
                {
                    "start_date": start.isoformat(),
                    "end_date": end.isoformat(),
                    "start_mjd": 60300.0,
                    "end_mjd": 60301.0,
                    "tile_id": 1,
                    "band_id": 2,
                }
            ],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["id"] == 1
    assert body[0]["start_mjd"] == 60300.0
