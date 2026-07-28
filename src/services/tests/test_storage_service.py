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
