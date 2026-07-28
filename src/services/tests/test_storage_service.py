from types import SimpleNamespace
from unittest.mock import MagicMock

from src.services.storage_service import S3StorageService

FAKE_CONFIG = SimpleNamespace(
    s3_endpoint_url="http://minio:9000",
    aws_access_key_id="testkey",
    aws_secret_access_key="testsecret",
    s3_bucket_name="test-bucket",
)


def test_init_builds_client_from_settings(mocker):
    """The service constructs a boto3 S3 client using endpoint and credentials from settings."""
    mock_client_factory = mocker.patch(
        "src.services.storage_service.boto3.client", return_value=MagicMock()
    )

    S3StorageService(config=FAKE_CONFIG)

    mock_client_factory.assert_called_once_with(
        "s3",
        endpoint_url="http://minio:9000",
        aws_access_key_id="testkey",
        aws_secret_access_key="testsecret",
        region_name="us-east-1",
    )


def test_upload_file_delegates_to_client_with_bucket(mocker):
    """upload_file forwards the local path, configured bucket, and key to boto3."""
    fake_client = MagicMock()
    mocker.patch(
        "src.services.storage_service.boto3.client", return_value=fake_client
    )

    svc = S3StorageService(config=FAKE_CONFIG)
    svc.upload_file("/tmp/local.fits", "prefix/remote.fits")

    fake_client.upload_file.assert_called_once_with(
        "/tmp/local.fits", "test-bucket", "prefix/remote.fits"
    )


def test_download_file_delegates_to_client_with_bucket(mocker):
    """download_file forwards the configured bucket, key, and local destination to boto3."""
    fake_client = MagicMock()
    mocker.patch(
        "src.services.storage_service.boto3.client", return_value=fake_client
    )

    svc = S3StorageService(config=FAKE_CONFIG)
    svc.download_file("prefix/remote.fits", "/tmp/local.fits")

    fake_client.download_file.assert_called_once_with(
        "test-bucket", "prefix/remote.fits", "/tmp/local.fits"
    )
