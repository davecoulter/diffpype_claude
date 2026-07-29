from unittest.mock import MagicMock

import astropy.units as u
from mocpy import MOC

from src.services.tile_service import (
    create_tiles,
    generate_tile_tessellation,
    tile_with_most_calibrations,
)


def test_generate_tile_tessellation_covers_a_small_cone_region():
    """Real, in-memory tessellation math: no mocking, matching the doc's testing directive."""
    moc_to_tile = MOC.from_cone(
        lon=180 * u.deg, lat=0 * u.deg, radius=0.1 * u.deg, max_depth=10
    )

    tiles = generate_tile_tessellation(
        tile_side_length_arc_min=6.0, moc_to_tile=moc_to_tile, overlap_in_arc_min=0.0
    )

    assert len(tiles) >= 1
    for tile in tiles:
        assert tile["name"].startswith("Tile_")
        assert isinstance(tile["footprint"], MOC)
        assert 178 <= tile["ra"] <= 182
        assert -2 <= tile["decl"] <= 2
        assert tile["delta_ra"] > 0
        assert tile["delta_decl"] > 0


def test_generate_tile_tessellation_only_keeps_tiles_that_intersect_the_region():
    """A larger tessellation grid than the target region still returns only overlapping tiles."""
    moc_to_tile = MOC.from_cone(
        lon=90 * u.deg, lat=45 * u.deg, radius=0.05 * u.deg, max_depth=12
    )

    tiles = generate_tile_tessellation(
        tile_side_length_arc_min=3.0, moc_to_tile=moc_to_tile
    )

    for tile in tiles:
        assert moc_to_tile.intersection(tile["footprint"]).sky_fraction > 0


def test_create_tiles_returns_empty_list_for_no_tiles():
    mock_db = MagicMock()
    assert create_tiles(mock_db, project_id=1, tiles=[]) == []
    mock_db.execute.assert_not_called()


def test_create_tiles_populates_healpix_index_from_ra_decl():
    """Every inserted Tile row must carry healpix_index=(ra, decl) (the column is NOT NULL)."""
    mock_db = MagicMock()
    # No created rows -> the association step does no further work.
    mock_db.execute.return_value.scalars.return_value.all.return_value = []
    tiles = [
        {
            "name": "T1",
            "ra": 150.0,
            "decl": 2.0,
            "delta_ra": 0.1,
            "delta_decl": 0.1,
            "footprint": None,
        }
    ]

    create_tiles(mock_db, project_id=7, tiles=tiles)

    # First execute() is the bulk Tile insert; its second positional arg is the rows list.
    rows = mock_db.execute.call_args_list[0].args[1]
    assert rows[0]["healpix_index"] == (150.0, 2.0)
    assert rows[0]["project_id"] == 7


def test_tile_with_most_calibrations_returns_the_best_tile_id():
    mock_db = MagicMock()
    mock_db.execute.return_value.first.return_value = MagicMock(tile_id=39)

    result = tile_with_most_calibrations(mock_db, [28, 34, 35, 39, 40])

    assert result == 39


def test_tile_with_most_calibrations_returns_none_when_no_tile_has_any():
    mock_db = MagicMock()
    mock_db.execute.return_value.first.return_value = None

    result = tile_with_most_calibrations(mock_db, [28, 29, 30])

    assert result is None
