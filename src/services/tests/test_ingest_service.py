from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from src.db.enums import JobStatus
from src.db.models import IngestBatch
from src.services.ingest_service import (
    _resolve_reference_ids,
    bulk_upsert_images_and_calibrations,
    create_ingest_batch,
    get_ingest_batch,
    parse_fits_headers,
)


def _fake_wcs():
    wcs = MagicMock()
    wcs.calc_footprint.return_value = np.array(
        [[10.0, 20.0], [10.1, 20.0], [10.1, 20.1], [10.0, 20.1]]
    )
    return wcs


def test_parse_fits_headers_extracts_expected_fields(mocker):
    header_sci = {
        "CRVAL1": 10.05,
        "CRVAL2": 20.05,
        "XPOSURE": 150.0,
        "MJD-AVG": 60310.5,
    }
    header_pri = {"TARGPROP": "TEST-TARGET", "INSTRUME": "NIRCam", "FILTER": "F150W"}

    def fake_getheader(path, ext):
        return header_sci if ext == "SCI" else header_pri

    mocker.patch(
        "src.services.ingest_service.fits.getheader", side_effect=fake_getheader
    )
    mocker.patch("src.services.ingest_service.WCS", return_value=_fake_wcs())
    mocker.patch(
        "src.services.ingest_service.proj_plane_pixel_scales",
        return_value=np.array([2.5e-5, 2.5e-5]),
    )
    fake_moc = MagicMock()
    mocker.patch(
        "src.services.ingest_service.MOC.from_polygon_skycoord", return_value=fake_moc
    )

    df = parse_fits_headers(["/tmp/jw00001_sci.fits"])

    assert len(df) == 1
    row = df.iloc[0]
    assert row["base_filename"] == "jw00001_sci.fits"
    assert row["current_file_ext"] == ".fits"
    assert row["ra"] == 10.05
    assert row["decl"] == 20.05
    assert row["exp_time"] == 150.0
    assert row["mjd_avg"] == 60310.5
    assert row["target_name"] == "TEST-TARGET"
    assert row["instrument_name"] == "NIRCam"
    assert row["band_name"] == "F150W"
    assert row["plate_scale"] == pytest.approx(2.5e-5 * 3600.0)
    assert row["footprint"] is fake_moc


def test_resolve_reference_ids_maps_names_to_ids():
    mock_db = MagicMock()
    # MagicMock(name=...) sets the mock's repr name, not a `.name` attribute; set explicitly.
    instrument = MagicMock()
    instrument.name = "NIRCam"
    instrument.id = 1
    band = MagicMock()
    band.name = "F150W"
    band.id = 2
    mock_db.query.return_value.all.side_effect = [[instrument], [band]]

    df = pd.DataFrame(
        [{"base_filename": "a.fits", "instrument_name": "NIRCam", "band_name": "F150W"}]
    )

    result = _resolve_reference_ids(mock_db, df)

    assert result.iloc[0]["instrument_id"] == 1
    assert result.iloc[0]["band_id"] == 2
    assert "instrument_name" not in result.columns
    assert "band_name" not in result.columns


def test_resolve_reference_ids_matches_case_insensitively():
    """Regression: real FITS headers write INSTRUME/FILTER in uppercase (e.g. "NIRCAM"),
    which doesn't match this project's mixed-case reference data ("NIRCam") on an
    exact-string lookup — a real ~20-file batch of real JWST data failed on this."""
    mock_db = MagicMock()
    instrument = MagicMock()
    instrument.name = "NIRCam"
    instrument.id = 1
    band = MagicMock()
    band.name = "F115W"
    band.id = 2
    mock_db.query.return_value.all.side_effect = [[instrument], [band]]

    df = pd.DataFrame(
        [{"base_filename": "a.fits", "instrument_name": "NIRCAM", "band_name": "F115W"}]
    )

    result = _resolve_reference_ids(mock_db, df)

    assert result.iloc[0]["instrument_id"] == 1
    assert result.iloc[0]["band_id"] == 2


def test_resolve_reference_ids_raises_on_unknown_instrument():
    mock_db = MagicMock()
    mock_db.query.return_value.all.side_effect = [[], []]

    df = pd.DataFrame(
        [{"base_filename": "a.fits", "instrument_name": "Unknown", "band_name": "F150W"}]
    )

    with pytest.raises(ValueError, match="Unknown instrument/band"):
        _resolve_reference_ids(mock_db, df)


def test_bulk_upsert_returns_zero_for_empty_dataframe():
    mock_db = MagicMock()
    assert bulk_upsert_images_and_calibrations(mock_db, 1, pd.DataFrame()) == 0
    mock_db.execute.assert_not_called()


def test_create_ingest_batch_dispatches_and_returns_ids(mocker):
    mock_db = MagicMock()
    mock_db.refresh.side_effect = lambda obj: setattr(obj, "id", 11)
    fake_result = MagicMock(id="ingest-task-id")
    mock_delay = mocker.patch(
        "src.worker.tasks.run_ingest_batch.delay", return_value=fake_result
    )

    job_id, batch_id = create_ingest_batch(mock_db, project_id=1, s3_prefix="raw/")

    assert job_id == "ingest-task-id"
    assert batch_id == 11
    mock_db.add.assert_called_once()
    added = mock_db.add.call_args[0][0]
    assert isinstance(added, IngestBatch)
    assert added.project_id == 1
    assert added.s3_prefix == "raw/"
    mock_delay.assert_called_once_with(11)


def test_create_ingest_batch_marks_failed_and_reraises_when_dispatch_fails(mocker):
    """If .delay() fails (e.g. broker unreachable), the already-committed row must not
    be left permanently PENDING with no task ever queued to redeliver it."""
    mock_db = MagicMock()
    mock_db.refresh.side_effect = lambda obj: setattr(obj, "id", 21)
    mocker.patch(
        "src.worker.tasks.run_ingest_batch.delay",
        side_effect=ConnectionError("broker unreachable"),
    )

    with pytest.raises(ConnectionError):
        create_ingest_batch(mock_db, project_id=1, s3_prefix="raw/")

    added = mock_db.add.call_args[0][0]
    assert added.status == JobStatus.FAILED
    assert mock_db.commit.call_count == 2


def test_get_ingest_batch_returns_batch_for_known_id():
    fake_batch = MagicMock(spec=IngestBatch)
    mock_db = MagicMock()
    mock_db.get.return_value = fake_batch

    result = get_ingest_batch(mock_db, 5)

    mock_db.get.assert_called_once_with(IngestBatch, 5)
    assert result is fake_batch


def test_get_ingest_batch_returns_none_for_unknown_id():
    mock_db = MagicMock()
    mock_db.get.return_value = None

    assert get_ingest_batch(mock_db, 999) is None
