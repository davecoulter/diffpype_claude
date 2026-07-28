import astropy.units as u
from mocpy import MOC

from src.db.spatial_types import moc_to_ranges, ranges_to_moc


def test_moc_to_ranges_returns_none_for_none():
    assert moc_to_ranges(None) is None


def test_ranges_to_moc_returns_none_for_none():
    assert ranges_to_moc(None) is None


def test_ranges_to_moc_returns_empty_moc_for_empty_list():
    moc = ranges_to_moc([])
    assert moc.empty()


def test_moc_to_ranges_round_trips_through_ranges_to_moc():
    original = MOC.from_cone(
        lon=10 * u.deg, lat=20 * u.deg, radius=0.5 * u.deg, max_depth=10
    )

    ranges = moc_to_ranges(original)
    restored = ranges_to_moc(ranges)

    assert isinstance(ranges, list)
    assert all(isinstance(r, tuple) and len(r) == 2 for r in ranges)
    assert (restored.to_depth29_ranges == original.to_depth29_ranges).all()
