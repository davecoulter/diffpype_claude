from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.db.enums import JobStatus
from src.db.models import Level3Mosaic
from src.db.session import get_db

VALID_PAYLOAD = {
    "project_id": 1,
    "tile_id": 2,
    "epoch_id": 3,
    "band_id": 4,
    "instrument_id": 5,
    "filename": "mosaic_1.fits",
    "target_plate_scale": 0.03,
}


@pytest.fixture
def mock_db():
    db = MagicMock()
    app.dependency_overrides[get_db] = lambda: db
    yield db
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def client():
    return TestClient(app)


def test_create_mosaic_returns_job_and_mosaic_id(client, mock_db, mocker):
    mocker.patch(
        "src.services.mosaic_service.create_mosaic",
        return_value=("fake-task-id", 8),
    )

    response = client.post("/api/v1/mosaics", json=VALID_PAYLOAD)

    assert response.status_code == 200
    assert response.json() == {"job_id": "fake-task-id", "mosaic_id": 8}


def test_get_mosaic_status_returns_mosaic(client, mock_db, mocker):
    mocker.patch(
        "src.services.mosaic_service.get_mosaic",
        return_value=Level3Mosaic(
            id=8,
            filename="mosaic_1.fits",
            target_plate_scale=0.03,
            footprint=None,
            ra=None,
            decl=None,
            status=JobStatus.PENDING,
            project_id=1,
            tile_id=2,
            epoch_id=3,
            band_id=4,
            instrument_id=5,
        ),
    )

    response = client.get("/api/v1/mosaics/8")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == 8
    assert body["status"] == "pending"
    assert "footprint" not in body


def test_get_mosaic_status_404_when_missing(client, mock_db, mocker):
    mocker.patch("src.services.mosaic_service.get_mosaic", return_value=None)

    response = client.get("/api/v1/mosaics/999")

    assert response.status_code == 404
