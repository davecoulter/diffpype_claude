"""Integration tests for S3StorageService against a live S3-compatible endpoint.

These prove the real network path (application -> S3-compatible endpoint) that
test_storage_service.py cannot: that file only mocks boto3. Requires a reachable
S3_ENDPOINT_URL (docker-compose's minio for container runs / CI; export a
localhost override for ad hoc host-side runs, matching the existing pattern for
DATABASE_URL/TEST_DATABASE_URL in src/db/tests/).
"""

import uuid

import botocore.exceptions
import pytest

from src.core.config import settings
from src.services.storage_service import S3StorageService


@pytest.fixture(scope="module")
def storage() -> S3StorageService:
    """Build a real S3StorageService and ensure its target bucket exists."""
    svc = S3StorageService(config=settings)
    try:
        svc._client.create_bucket(Bucket=settings.s3_bucket_name)
    except botocore.exceptions.ClientError:
        pass  # bucket already exists from a prior run
    return svc


def test_upload_then_download_round_trips_content(storage, tmp_path):
    """A file uploaded to the real bucket and downloaded back has identical bytes."""
    key = f"integration-tests/{uuid.uuid4()}.txt"
    src_path = tmp_path / "upload.txt"
    src_path.write_text("diffpype-integration-roundtrip")

    storage.upload_file(str(src_path), key)
    dst_path = tmp_path / "download.txt"
    storage.download_file(key, str(dst_path))

    assert dst_path.read_text() == "diffpype-integration-roundtrip"
    storage._client.delete_object(Bucket=settings.s3_bucket_name, Key=key)


def test_download_of_missing_key_raises(storage, tmp_path):
    """Downloading a key that was never uploaded raises a clear client error, not a silent no-op."""
    dst_path = tmp_path / "should_not_exist.txt"
    with pytest.raises(botocore.exceptions.ClientError):
        storage.download_file(
            f"integration-tests/{uuid.uuid4()}-missing.txt", str(dst_path)
        )
