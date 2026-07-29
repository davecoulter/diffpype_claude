import astropy.units as u
from mocpy import MOC
from sqlalchemy.dialects.postgresql import MultiRange, Range

from src.db.spatial_types import (
    MOCType,
    PointHEALPixType,
    _point_to_depth29_cell,
    moc_to_ranges,
    ranges_to_moc,
)


def test_point_to_depth29_cell_is_a_stable_positive_int():
    cell = _point_to_depth29_cell(180.0, 0.0)
    assert isinstance(cell, int)
    assert 0 <= cell < 12 * 4**29  # within the depth-29 NESTED cell range
    # Deterministic: the same coordinate always maps to the same cell.
    assert _point_to_depth29_cell(180.0, 0.0) == cell


def test_point_healpix_bind_encodes_tuple_as_single_cell_range():
    cell = _point_to_depth29_cell(150.12, 2.31)

    bound = PointHEALPixType().process_bind_param((150.12, 2.31), None)

    assert isinstance(bound, Range)
    assert bound.lower == cell
    assert bound.upper == cell + 1


def test_point_healpix_result_decodes_range_to_cell_index():
    cell = 190633879269976798
    decoded = PointHEALPixType().process_result_value(
        Range(cell, cell + 1, bounds="[)"), None
    )
    assert decoded == cell


def test_point_healpix_bind_and_result_round_trip():
    hpx = PointHEALPixType()
    expected = _point_to_depth29_cell(10.68, 41.27)

    bound = hpx.process_bind_param((10.68, 41.27), None)
    decoded = hpx.process_result_value(bound, None)

    assert decoded == expected


def test_point_healpix_none_passes_through_both_directions():
    hpx = PointHEALPixType()
    assert hpx.process_bind_param(None, None) is None
    assert hpx.process_result_value(None, None) is None


def test_moc_type_binds_a_native_multirange_and_reads_back_a_moc():
    moc = MOC.from_cone(
        lon=10 * u.deg, lat=20 * u.deg, radius=0.5 * u.deg, max_depth=10
    )
    moctype = MOCType()

    bound = moctype.process_bind_param(moc, None)
    assert isinstance(bound, MultiRange)
    assert all(isinstance(r, Range) for r in bound)

    restored = moctype.process_result_value(bound, None)
    assert (restored.to_depth29_ranges == moc.to_depth29_ranges).all()


def test_moc_type_none_passes_through_both_directions():
    moctype = MOCType()
    assert moctype.process_bind_param(None, None) is None
    assert moctype.process_result_value(None, None) is None


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
