from unittest.mock import MagicMock

import astropy.units as u
import pytest
from mocpy import MOC

from src.db.enums import JobStatus
from src.db.models import Level3Mosaic
from src.services.mosaic_service import (
    _unioned_footprint_and_barycenter,
    create_mosaic,
    get_mosaic,
)


def test_unioned_footprint_and_barycenter_unions_and_extracts_center():
    """Real, in-memory MOC math: two adjacent cones union into one footprint with a center between them."""
    moc_a = MOC.from_cone(lon=10 * u.deg, lat=0 * u.deg, radius=0.2 * u.deg, max_depth=12)
    moc_b = MOC.from_cone(lon=10.3 * u.deg, lat=0 * u.deg, radius=0.2 * u.deg, max_depth=12)

    union, ra, decl = _unioned_footprint_and_barycenter([moc_a, moc_b])

    assert union.sky_fraction >= moc_a.sky_fraction
    assert union.sky_fraction >= moc_b.sky_fraction
    assert 9.5 <= ra <= 10.8
    assert -0.5 <= decl <= 0.5


def test_unioned_footprint_and_barycenter_single_moc_is_a_no_op_union():
    moc = MOC.from_cone(lon=50 * u.deg, lat=20 * u.deg, radius=0.1 * u.deg, max_depth=10)

    union, ra, decl = _unioned_footprint_and_barycenter([moc])

    assert (union.to_depth29_ranges == moc.to_depth29_ranges).all()


def test_create_mosaic_dispatches_and_returns_ids(mocker):
    mock_db = MagicMock()
    mock_db.execute.return_value.all.return_value = []  # no constituent calibrations
    mock_db.refresh.side_effect = lambda obj: setattr(obj, "id", 42)
    fake_result = MagicMock(id="mosaic-task-id")
    mock_delay = mocker.patch(
        "src.worker.tasks.run_mosaic_drizzle.delay", return_value=fake_result
    )

    job_id, mosaic_id = create_mosaic(
        mock_db,
        project_id=1,
        tile_id=2,
        epoch_id=3,
        band_id=4,
        instrument_id=5,
        filename="mosaic_1.fits",
        target_plate_scale=0.03,
    )

    assert job_id == "mosaic-task-id"
    assert mosaic_id == 42
    added = mock_db.add.call_args[0][0]
    assert isinstance(added, Level3Mosaic)
    assert added.footprint is None
    assert added.ra is None
    assert added.decl is None
    mock_delay.assert_called_once_with(42)


def test_create_mosaic_computes_footprint_and_barycenter_when_calibrations_exist(mocker):
    moc_a = MOC.from_cone(lon=10 * u.deg, lat=20 * u.deg, radius=0.05 * u.deg, max_depth=12)
    mock_db = MagicMock()
    mock_db.execute.return_value.all.return_value = [(moc_a,)]
    mock_db.refresh.side_effect = lambda obj: setattr(obj, "id", 7)
    mocker.patch(
        "src.worker.tasks.run_mosaic_drizzle.delay", return_value=MagicMock(id="x")
    )

    create_mosaic(
        mock_db,
        project_id=1,
        tile_id=2,
        epoch_id=3,
        band_id=4,
        instrument_id=5,
        filename="mosaic_2.fits",
        target_plate_scale=0.03,
    )

    added = mock_db.add.call_args[0][0]
    assert added.footprint is not None
    assert added.ra == pytest.approx(10.0, abs=0.1)
    assert added.decl == pytest.approx(20.0, abs=0.1)


def test_create_mosaic_marks_failed_and_reraises_when_dispatch_fails(mocker):
    """If .delay() fails (e.g. broker unreachable), the already-committed row must not
    be left permanently PENDING with no task ever queued to redeliver it."""
    mock_db = MagicMock()
    mock_db.execute.return_value.all.return_value = []
    mock_db.refresh.side_effect = lambda obj: setattr(obj, "id", 13)
    mocker.patch(
        "src.worker.tasks.run_mosaic_drizzle.delay",
        side_effect=ConnectionError("broker unreachable"),
    )

    with pytest.raises(ConnectionError):
        create_mosaic(
            mock_db,
            project_id=1,
            tile_id=2,
            epoch_id=3,
            band_id=4,
            instrument_id=5,
            filename="mosaic_3.fits",
            target_plate_scale=0.03,
        )

    added = mock_db.add.call_args[0][0]
    assert added.status == JobStatus.FAILED
    assert mock_db.commit.call_count == 2


def test_get_mosaic_returns_mosaic_for_known_id():
    fake_mosaic = MagicMock(spec=Level3Mosaic)
    mock_db = MagicMock()
    mock_db.get.return_value = fake_mosaic

    result = get_mosaic(mock_db, 9)

    mock_db.get.assert_called_once_with(Level3Mosaic, 9)
    assert result is fake_mosaic


def test_get_mosaic_returns_none_for_unknown_id():
    mock_db = MagicMock()
    mock_db.get.return_value = None

    assert get_mosaic(mock_db, 999) is None
