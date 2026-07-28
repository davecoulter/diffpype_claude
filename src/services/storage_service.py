"""S3-compatible object storage access for FITS payloads, shared by API and CLI."""

import boto3

from src.core.config import Settings, settings


class S3StorageService:
    """Thin boto3 wrapper for uploading and downloading files to an S3-compatible bucket."""

    def __init__(self, config: Settings = settings) -> None:
        """Build an S3 client and bind the target bucket from application settings."""
        self._bucket = config.s3_bucket_name
        self._client = boto3.client(
            "s3",
            endpoint_url=config.s3_endpoint_url,
            aws_access_key_id=config.aws_access_key_id,
            aws_secret_access_key=config.aws_secret_access_key,
            region_name="us-east-1",
        )

    def upload_file(self, local_path: str, s3_key: str) -> None:
        """Upload a local file to the configured bucket under the given S3 key."""
        self._client.upload_file(local_path, self._bucket, s3_key)

    def download_file(self, s3_key: str, local_path: str) -> None:
        """Download the object at the given S3 key from the configured bucket to a local path."""
        self._client.download_file(self._bucket, s3_key, local_path)
