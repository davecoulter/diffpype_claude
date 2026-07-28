from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from mocpy import MOC

from src.api.main import app
from src.db.models import Tile
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


def test_tessellate_tiles_returns_preview_without_writing(client, mocker):
    fake_moc = MOC.new_empty(10)
    mocker.patch(
        "src.services.tile_service.generate_tile_tessellation",
        return_value=[
            {
                "name": "Tile_1",
                "ra": 10.0,
                "decl": 20.0,
                "delta_ra": 0.1,
                "delta_decl": 0.1,
                "footprint": fake_moc,
            }
        ],
    )

    response = client.post(
        "/api/v1/tiles/tessellate",
        json={
            "project_id": 1,
            "tile_side_length_arc_min": 6.0,
            "moc_to_tile": [[0, 10]],
            "overlap_in_arc_min": 0.0,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["name"] == "Tile_1"
    assert body[0]["footprint"] == []  # new_empty MOC has no ranges


def test_create_tiles_returns_persisted_tiles(client, mock_db, mocker):
    mocker.patch(
        "src.services.tile_service.create_tiles",
        return_value=[
            Tile(
                id=1,
                name="Tile_1",
                ra=10.0,
                decl=20.0,
                delta_ra=0.1,
                delta_decl=0.1,
                footprint=None,
                project_id=1,
            )
        ],
    )

    response = client.post(
        "/api/v1/tiles",
        json={
            "project_id": 1,
            "tiles": [
                {
                    "name": "Tile_1",
                    "ra": 10.0,
                    "decl": 20.0,
                    "delta_ra": 0.1,
                    "delta_decl": 0.1,
                    "footprint": None,
                }
            ],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body == [
        {
            "id": 1,
            "name": "Tile_1",
            "ra": 10.0,
            "decl": 20.0,
            "delta_ra": 0.1,
            "delta_decl": 0.1,
            "footprint": None,
            "project_id": 1,
        }
    ]
