"""Object storage access for FITS payloads, shared by API and CLI.

Two interchangeable backends implement the same `StorageBackend` protocol:
`S3StorageService` (S3-compatible, e.g. MinIO) and `LocalStorageService`
(host filesystem, for local dev without Docker/MinIO). `get_storage_service`
selects between them via the `STORAGE_BACKEND` setting.
"""

import shutil
from pathlib import Path
from typing import Protocol, runtime_checkable

import boto3

from src.core.config import Settings, settings


@runtime_checkable
class StorageBackend(Protocol):
    """Common interface for uploading and downloading files by storage key."""

    def upload_file(self, local_path: str, key: str) -> None:
        """Upload a local file to storage under the given key."""
        ...

    def download_file(self, key: str, local_path: str) -> None:
        """Download the object at the given key from storage to a local path."""
        ...

    def list_prefix(self, prefix: str) -> list[str]:
        """Return all object keys under the given prefix."""
        ...


class S3StorageService:
    """Thin boto3 wrapper for uploading and downloading files to an S3-compatible bucket."""

    def __init__(self, config: Settings = settings) -> None:
        """Build an S3 client and bind the target bucket from application settings.

        Credentials and endpoint are only passed to boto3 when actually
        configured (non-empty) — leaving them unset lets boto3's default
        credential chain resolve real IAM role credentials (EC2/ECS/IRSA) and
        AWS's real regional endpoints in a cloud deployment, instead of
        forcing MinIO's dev-only static-credential shape everywhere. Region is
        configurable rather than hardcoded, since real deployments aren't
        always us-east-1.
        """
        self._bucket = config.s3_bucket_name
        client_kwargs: dict = {"region_name": config.s3_region}
        if config.s3_endpoint_url:
            client_kwargs["endpoint_url"] = config.s3_endpoint_url
        if config.aws_access_key_id and config.aws_secret_access_key:
            client_kwargs["aws_access_key_id"] = config.aws_access_key_id
            client_kwargs["aws_secret_access_key"] = config.aws_secret_access_key
        self._client = boto3.client("s3", **client_kwargs)

    def upload_file(self, local_path: str, key: str) -> None:
        """Upload a local file to the configured bucket under the given key."""
        self._client.upload_file(local_path, self._bucket, key)

    def download_file(self, key: str, local_path: str) -> None:
        """Download the object at the given key from the configured bucket to a local path."""
        self._client.download_file(self._bucket, key, local_path)

    def list_prefix(self, prefix: str) -> list[str]:
        """Return all object keys under the given prefix in the configured bucket."""
        paginator = self._client.get_paginator("list_objects_v2")
        keys: list[str] = []
        for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix):
            keys.extend(obj["Key"] for obj in page.get("Contents", []))
        return keys


class LocalStorageService:
    """Filesystem-backed storage service rooted at a configured local directory.

    Auto-creates its root directory if missing (a different risk profile than
    the S3 bucket, which is deliberately never auto-created by this codebase).
    """

    def __init__(self, config: Settings = settings) -> None:
        """Bind the storage root from application settings and create it if missing."""
        self._root = Path(config.local_storage_root)
        self._root.mkdir(parents=True, exist_ok=True)

    def upload_file(self, local_path: str, key: str) -> None:
        """Copy a local file into the storage root under the given key."""
        destination = self._root / key
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(local_path, destination)

    def download_file(self, key: str, local_path: str) -> None:
        """Copy the file at the given key from the storage root to a local path."""
        source = self._root / key
        if not source.is_file():
            raise FileNotFoundError(f"No object at key '{key}' under {self._root}")
        shutil.copyfile(source, local_path)

    def list_prefix(self, prefix: str) -> list[str]:
        """Return all relative keys under the given prefix in the storage root."""
        base = self._root / prefix
        if not base.is_dir():
            return []
        return sorted(
            str(p.relative_to(self._root)) for p in base.rglob("*") if p.is_file()
        )


def get_storage_service(config: Settings = settings) -> StorageBackend:
    """Return the configured storage backend: `S3StorageService` or `LocalStorageService`."""
    if config.storage_backend == "local":
        return LocalStorageService(config)
    return S3StorageService(config)
