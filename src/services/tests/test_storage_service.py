from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.services.storage_service import (
    LocalStorageService,
    S3StorageService,
    get_storage_service,
)

FAKE_CONFIG = SimpleNamespace(
    s3_endpoint_url="http://minio:9000",
    aws_access_key_id="testkey",
    aws_secret_access_key="testsecret",
    s3_bucket_name="test-bucket",
    s3_region="us-east-1",
)


def test_init_builds_client_from_settings(mocker):
    """The service constructs a boto3 S3 client using endpoint, region, and credentials from settings."""
    mock_client_factory = mocker.patch(
        "src.services.storage_service.boto3.client", return_value=MagicMock()
    )

    S3StorageService(config=FAKE_CONFIG)

    mock_client_factory.assert_called_once_with(
        "s3",
        region_name="us-east-1",
        endpoint_url="http://minio:9000",
        aws_access_key_id="testkey",
        aws_secret_access_key="testsecret",
    )


def test_init_uses_configured_region(mocker):
    mock_client_factory = mocker.patch(
        "src.services.storage_service.boto3.client", return_value=MagicMock()
    )
    config = SimpleNamespace(
        s3_endpoint_url="http://minio:9000",
        aws_access_key_id="testkey",
        aws_secret_access_key="testsecret",
        s3_bucket_name="test-bucket",
        s3_region="eu-west-1",
    )

    S3StorageService(config=config)

    assert mock_client_factory.call_args.kwargs["region_name"] == "eu-west-1"


def test_init_omits_credentials_when_unset_so_boto3_falls_back_to_iam(mocker):
    """A cloud deployment leaves these blank to use its IAM role instead of static creds."""
    mock_client_factory = mocker.patch(
        "src.services.storage_service.boto3.client", return_value=MagicMock()
    )
    config = SimpleNamespace(
        s3_endpoint_url="",
        aws_access_key_id="",
        aws_secret_access_key="",
        s3_bucket_name="test-bucket",
        s3_region="us-east-1",
    )

    S3StorageService(config=config)

    mock_client_factory.assert_called_once_with("s3", region_name="us-east-1")


def test_init_omits_only_endpoint_when_credentials_are_still_set(mocker):
    mock_client_factory = mocker.patch(
        "src.services.storage_service.boto3.client", return_value=MagicMock()
    )
    config = SimpleNamespace(
        s3_endpoint_url="",
        aws_access_key_id="testkey",
        aws_secret_access_key="testsecret",
        s3_bucket_name="test-bucket",
        s3_region="us-east-1",
    )

    S3StorageService(config=config)

    mock_client_factory.assert_called_once_with(
        "s3",
        region_name="us-east-1",
        aws_access_key_id="testkey",
        aws_secret_access_key="testsecret",
    )


def test_upload_file_delegates_to_client_with_bucket(mocker):
    """upload_file forwards the local path, configured bucket, and key to boto3."""
    fake_client = MagicMock()
    mocker.patch("src.services.storage_service.boto3.client", return_value=fake_client)

    svc = S3StorageService(config=FAKE_CONFIG)
    svc.upload_file("/tmp/local.fits", "prefix/remote.fits")

    fake_client.upload_file.assert_called_once_with(
        "/tmp/local.fits", "test-bucket", "prefix/remote.fits"
    )


def test_download_file_delegates_to_client_with_bucket(mocker):
    """download_file forwards the configured bucket, key, and local destination to boto3."""
    fake_client = MagicMock()
    mocker.patch("src.services.storage_service.boto3.client", return_value=fake_client)

    svc = S3StorageService(config=FAKE_CONFIG)
    svc.download_file("prefix/remote.fits", "/tmp/local.fits")

    fake_client.download_file.assert_called_once_with(
        "test-bucket", "prefix/remote.fits", "/tmp/local.fits"
    )


def test_local_storage_service_creates_root_if_missing(tmp_path):
    """Instantiating LocalStorageService auto-creates a missing storage root."""
    root = tmp_path / "does" / "not" / "exist"
    config = SimpleNamespace(local_storage_root=str(root))

    LocalStorageService(config=config)

    assert root.is_dir()


def test_local_storage_service_upload_then_download_round_trips_content(tmp_path):
    """A file uploaded under a nested key and downloaded back has identical bytes."""
    config = SimpleNamespace(local_storage_root=str(tmp_path / "root"))
    svc = LocalStorageService(config=config)
    src = tmp_path / "upload.txt"
    src.write_text("diffpype-local-roundtrip")

    svc.upload_file(str(src), "raw/upload.txt")
    dst = tmp_path / "download.txt"
    svc.download_file("raw/upload.txt", str(dst))

    assert dst.read_text() == "diffpype-local-roundtrip"


def test_s3_storage_service_list_prefix_paginates_all_pages(mocker):
    """list_prefix aggregates keys across multiple paginator pages."""
    fake_paginator = MagicMock()
    fake_paginator.paginate.return_value = [
        {"Contents": [{"Key": "raw/a.fits"}, {"Key": "raw/b.fits"}]},
        {"Contents": [{"Key": "raw/c.fits"}]},
    ]
    fake_client = MagicMock()
    fake_client.get_paginator.return_value = fake_paginator
    mocker.patch("src.services.storage_service.boto3.client", return_value=fake_client)

    svc = S3StorageService(config=FAKE_CONFIG)
    keys = svc.list_prefix("raw/")

    assert keys == ["raw/a.fits", "raw/b.fits", "raw/c.fits"]
    fake_client.get_paginator.assert_called_once_with("list_objects_v2")


def test_s3_storage_service_list_prefix_empty_when_no_contents(mocker):
    fake_paginator = MagicMock()
    fake_paginator.paginate.return_value = [{}]
    fake_client = MagicMock()
    fake_client.get_paginator.return_value = fake_paginator
    mocker.patch("src.services.storage_service.boto3.client", return_value=fake_client)

    svc = S3StorageService(config=FAKE_CONFIG)

    assert svc.list_prefix("empty/") == []


def test_local_storage_service_list_prefix_returns_files_under_prefix(tmp_path):
    config = SimpleNamespace(local_storage_root=str(tmp_path / "root"))
    svc = LocalStorageService(config=config)
    svc.upload_file(str(_write(tmp_path, "a.fits")), "raw/a.fits")
    svc.upload_file(str(_write(tmp_path, "b.fits")), "raw/b.fits")
    svc.upload_file(str(_write(tmp_path, "c.fits")), "other/c.fits")

    assert svc.list_prefix("raw") == ["raw/a.fits", "raw/b.fits"]


def test_local_storage_service_list_prefix_empty_when_prefix_missing(tmp_path):
    config = SimpleNamespace(local_storage_root=str(tmp_path / "root"))
    svc = LocalStorageService(config=config)

    assert svc.list_prefix("nope") == []


def test_local_list_prefix_matches_partial_filename_prefix(tmp_path):
    """A narrow prefix like 'raw/jw0123' matches by string, not by requiring a directory."""
    config = SimpleNamespace(local_storage_root=str(tmp_path / "root"))
    svc = LocalStorageService(config=config)
    svc.upload_file(str(_write(tmp_path, "a")), "raw/jw0123_nrca.fits")
    svc.upload_file(str(_write(tmp_path, "b")), "raw/jw0999_nrcb.fits")

    assert svc.list_prefix("raw/jw0123") == ["raw/jw0123_nrca.fits"]


def test_local_list_prefix_empty_when_prefix_and_parent_both_missing(tmp_path):
    """A deep prefix whose parent directory also doesn't exist returns []."""
    config = SimpleNamespace(local_storage_root=str(tmp_path / "root"))
    svc = LocalStorageService(config=config)

    assert svc.list_prefix("no/such/deep") == []


def test_local_list_prefix_excludes_dot_files(tmp_path):
    """A partially-downloaded hidden file (dot-prefixed) is never surfaced as a key."""
    config = SimpleNamespace(local_storage_root=str(tmp_path / "root"))
    svc = LocalStorageService(config=config)
    svc.upload_file(str(_write(tmp_path, "a")), "raw/good.fits")
    svc.upload_file(str(_write(tmp_path, "b")), "raw/.inflight.tmp")

    assert svc.list_prefix("raw") == ["raw/good.fits"]


# --- Staging → canonical sync (mc mirror) ---

_LOCAL_SYNC_CONFIG = SimpleNamespace(
    storage_backend="local", local_storage_root="/data"
)
_S3_SYNC_CONFIG = SimpleNamespace(
    storage_backend="s3",
    s3_endpoint_url="http://minio:9000",
    aws_access_key_id="key",
    aws_secret_access_key="secret",
    s3_bucket_name="bucket",
)


def _fake_mc_process(lines, return_code=0):
    proc = MagicMock()
    proc.stdout = iter(lines)
    proc.wait.return_value = return_code
    return proc


def test_resolve_mc_canonical_target_local_is_a_filesystem_path():
    from src.services.storage_service import _resolve_mc_canonical_target

    assert _resolve_mc_canonical_target(_LOCAL_SYNC_CONFIG, "raw") == "/data/raw"


def test_resolve_mc_canonical_target_s3_registers_alias_and_qualifies_bucket(mocker):
    run = mocker.patch("src.services.storage_service.subprocess.run")
    from src.services.storage_service import _resolve_mc_canonical_target

    target = _resolve_mc_canonical_target(_S3_SYNC_CONFIG, "raw")

    assert target == "diffpype-canonical/bucket/raw"
    assert run.call_args[0][0][:3] == ["mc", "alias", "set"]


def test_resolve_mc_canonical_target_s3_empty_prefix_is_bucket_root(mocker):
    mocker.patch("src.services.storage_service.subprocess.run")
    from src.services.storage_service import _resolve_mc_canonical_target

    assert (
        _resolve_mc_canonical_target(_S3_SYNC_CONFIG, "") == "diffpype-canonical/bucket"
    )


# Real event shapes, empirically confirmed by running `mc --json mirror` against
# a live MinIO instance with real FITS files (not assumed/fabricated) — see doc
# 30's Logs. Per-file success events carry cumulative totalCount/totalSize; the
# trailing summary event has no target/source at all; errors carry status=="error".
_REAL_FILE_EVENT_A = (
    '{"status":"success","source":"/staging/a.fits","target":"canonical/a.fits",'
    '"size":100,"totalCount":1,"totalSize":100,"eventTime":"","eventType":""}'
)
_REAL_FILE_EVENT_B = (
    '{"status":"success","source":"/staging/b.fits","target":"canonical/b.fits",'
    '"size":50,"totalCount":2,"totalSize":150,"eventTime":"","eventType":""}'
)
_REAL_SUMMARY_EVENT = (
    '{"status":"success","total":150,"transferred":150,'
    '"duration":1971842875,"speed":178878025.46}'
)
_REAL_ERROR_EVENT = (
    '{"status":"error","error":{"message":"Failed to perform mirroring",'
    '"cause":{"message":"The specified bucket does not exist"},"type":"error"}}'
)


def test_sync_staging_to_canonical_streams_mc_json_events(mocker):
    """The sync invokes `mc --json mirror` and consumes its per-file event stream."""
    popen = mocker.patch(
        "src.services.storage_service.subprocess.Popen",
        return_value=_fake_mc_process([_REAL_FILE_EVENT_A, "", _REAL_FILE_EVENT_B]),
    )
    from src.services.storage_service import sync_staging_to_canonical

    sync_staging_to_canonical("/staging", "canonical", config=_LOCAL_SYNC_CONFIG)

    cmd = popen.call_args[0][0]
    assert cmd[:3] == ["mc", "--json", "mirror"]
    assert cmd[3] == "/staging"
    assert cmd[4] == "/data/canonical"


def test_sync_staging_to_canonical_does_not_miscount_the_trailing_summary_event(mocker):
    """Regression: the trailing job-summary line has no target/source and must
    not be counted as a copied file (it previously was, over-counting by one)."""
    mocker.patch(
        "src.services.storage_service.subprocess.Popen",
        return_value=_fake_mc_process(
            [_REAL_FILE_EVENT_A, _REAL_FILE_EVENT_B, _REAL_SUMMARY_EVENT]
        ),
    )
    mock_log = MagicMock()
    mocker.patch("src.services.storage_service.get_logger", return_value=mock_log)
    from src.services.storage_service import sync_staging_to_canonical

    sync_staging_to_canonical("/staging", "canonical", config=_LOCAL_SYNC_CONFIG)

    copied_calls = [
        c
        for c in mock_log.info.call_args_list
        if c.args[0] == "staging_sync_file_copied"
    ]
    summary_calls = [
        c
        for c in mock_log.info.call_args_list
        if c.args[0] == "staging_sync_job_summary"
    ]
    assert len(copied_calls) == 2  # exactly the two real files, not three
    assert copied_calls[-1].kwargs["index"] == 2
    assert len(summary_calls) == 1
    assert summary_calls[0].kwargs["transferred_bytes"] == 150


def test_sync_staging_to_canonical_logs_error_events_without_counting_them(mocker):
    mocker.patch(
        "src.services.storage_service.subprocess.Popen",
        return_value=_fake_mc_process(
            [_REAL_ERROR_EVENT, _REAL_SUMMARY_EVENT], return_code=1
        ),
    )
    mock_log = MagicMock()
    mocker.patch("src.services.storage_service.get_logger", return_value=mock_log)
    from src.services.storage_service import sync_staging_to_canonical

    with pytest.raises(RuntimeError, match="mc mirror exited with code 1"):
        sync_staging_to_canonical("/staging", "canonical", config=_LOCAL_SYNC_CONFIG)

    error_calls = [
        c
        for c in mock_log.warning.call_args_list
        if c.args[0] == "staging_sync_file_error"
    ]
    assert len(error_calls) == 1
    assert "does not exist" in error_calls[0].kwargs["error"]["cause"]["message"]


def test_sync_staging_to_canonical_raises_on_nonzero_exit(mocker):
    mocker.patch(
        "src.services.storage_service.subprocess.Popen",
        return_value=_fake_mc_process([_REAL_FILE_EVENT_A], return_code=1),
    )
    from src.services.storage_service import sync_staging_to_canonical

    with pytest.raises(RuntimeError, match="mc mirror exited with code 1"):
        sync_staging_to_canonical("/staging", "canonical", config=_LOCAL_SYNC_CONFIG)


def test_sync_staging_to_canonical_kills_subprocess_on_soft_time_limit(mocker):
    """A hang (SoftTimeLimitExceeded, raised by Celery inside the loop) must kill
    the mc subprocess rather than leave it orphaned, then re-raise."""
    from celery.exceptions import SoftTimeLimitExceeded

    def _hanging_stdout():
        yield _REAL_FILE_EVENT_A
        raise SoftTimeLimitExceeded()

    proc = MagicMock()
    proc.stdout = _hanging_stdout()
    mocker.patch("src.services.storage_service.subprocess.Popen", return_value=proc)
    from src.services.storage_service import sync_staging_to_canonical

    with pytest.raises(SoftTimeLimitExceeded):
        sync_staging_to_canonical("/staging", "canonical", config=_LOCAL_SYNC_CONFIG)

    proc.kill.assert_called_once()
    proc.wait.assert_called_once()


def test_sync_staging_to_canonical_skips_unparseable_lines(mocker):
    """A non-JSON progress line is logged and skipped, never fatal."""
    mocker.patch(
        "src.services.storage_service.subprocess.Popen",
        return_value=_fake_mc_process(["not-json-noise", _REAL_FILE_EVENT_A]),
    )
    from src.services.storage_service import sync_staging_to_canonical

    # Must not raise despite the malformed first line.
    sync_staging_to_canonical("/staging", "", config=_LOCAL_SYNC_CONFIG)


def test_dispatch_staging_sync_delays_task_and_returns_job_id(mocker):
    fake_result = MagicMock(id="sync-job-1")
    delay = mocker.patch(
        "src.worker.tasks.run_staging_sync.delay", return_value=fake_result
    )
    from src.services.storage_service import dispatch_staging_sync

    assert dispatch_staging_sync("/staging", "raw") == "sync-job-1"
    delay.assert_called_once_with("/staging", "raw")


def _write(tmp_path, name: str):
    path = tmp_path / name
    path.write_text("x")
    return path


def test_local_storage_service_download_of_missing_key_raises(tmp_path):
    """Downloading a key that was never uploaded raises FileNotFoundError, not a silent no-op."""
    config = SimpleNamespace(local_storage_root=str(tmp_path / "root"))
    svc = LocalStorageService(config=config)

    with pytest.raises(FileNotFoundError):
        svc.download_file("raw/missing.txt", str(tmp_path / "out.txt"))


def test_get_storage_service_returns_s3_by_default(mocker):
    mocker.patch("src.services.storage_service.boto3.client", return_value=MagicMock())
    config = SimpleNamespace(storage_backend="s3", **FAKE_CONFIG.__dict__)

    svc = get_storage_service(config=config)

    assert isinstance(svc, S3StorageService)


def test_get_storage_service_returns_local_when_configured(tmp_path):
    config = SimpleNamespace(
        storage_backend="local", local_storage_root=str(tmp_path / "root")
    )

    svc = get_storage_service(config=config)

    assert isinstance(svc, LocalStorageService)
