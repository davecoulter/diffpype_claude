from unittest.mock import MagicMock

import numpy as np
import pytest

from src.services.epoch_service import _cluster_mjds, cluster_epochs, create_epochs


def test_cluster_mjds_groups_two_tight_clusters_into_two_epochs():
    """Real, in-memory clustering math: two tight MJD groups separated by a gap."""
    cluster_a = [60300.0, 60300.1, 60300.2, 60300.3]
    cluster_b = [60350.0, 60350.1, 60350.2, 60350.3]

    intervals = _cluster_mjds(cluster_a + cluster_b, peak_distance_thresh=5.0)

    assert len(intervals) == 2
    (lo1, hi1), (lo2, hi2) = sorted(intervals.tolist())
    assert lo1 <= min(cluster_a) and hi1 >= max(cluster_a)
    assert lo2 <= min(cluster_b) and hi2 >= max(cluster_b)


def test_cluster_mjds_falls_back_to_one_cluster_when_no_peaks_detected():
    """A single tight group with a huge distance threshold must not crash KMeans(n_clusters=0)."""
    intervals = _cluster_mjds([60300.0, 60300.1, 60300.2], peak_distance_thresh=1000.0)

    assert len(intervals) == 1


def test_cluster_epochs_returns_empty_list_when_no_calibrations(mocker):
    mock_db = MagicMock()
    mock_db.execute.return_value.all.return_value = []

    result = cluster_epochs(
        mock_db, project_id=1, tile_id=1, band_id=1, peak_distance_thresh=5.0
    )

    assert result == []


def test_cluster_epochs_builds_epoch_dicts_from_clustered_mjds(mocker):
    mock_db = MagicMock()
    mock_db.execute.return_value.all.return_value = [
        (1, 60300.0),
        (2, 60300.1),
    ]
    mocker.patch(
        "src.services.epoch_service._cluster_mjds",
        return_value=np.array([[60299, 60302]]),
    )

    result = cluster_epochs(
        mock_db, project_id=1, tile_id=7, band_id=2, peak_distance_thresh=5.0
    )

    assert len(result) == 1
    epoch = result[0]
    assert epoch["start_mjd"] == 60299.0
    assert epoch["end_mjd"] == 60302.0
    assert epoch["tile_id"] == 7
    assert epoch["band_id"] == 2
    assert "start_date" in epoch and "end_date" in epoch


def test_create_epochs_returns_empty_list_for_no_epochs():
    mock_db = MagicMock()
    assert create_epochs(mock_db, project_id=1, epochs=[]) == []
    mock_db.execute.assert_not_called()
