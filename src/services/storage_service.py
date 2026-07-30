"""Object storage access for FITS payloads, shared by API and CLI.

Two interchangeable backends implement the same `StorageBackend` protocol:
`S3StorageService` (S3-compatible, e.g. MinIO) and `LocalStorageService`
(host filesystem, for local dev without Docker/MinIO). `get_storage_service`
selects between them via the `STORAGE_BACKEND` setting.
"""

import json
import shutil
import subprocess
from pathlib import Path
from typing import Protocol, runtime_checkable

import boto3
from celery.exceptions import SoftTimeLimitExceeded

from src.core.config import Settings, settings
from src.core.logger import get_logger

# Reused, idempotently-registered `mc` alias name for the canonical S3/MinIO
# endpoint. `mc alias set` is a no-op overwrite when re-run with the same values.
_MC_CANONICAL_ALIAS = "diffpype-canonical"


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
        """Return all relative keys whose path string starts with the given prefix.

        Matches S3's pure string-prefix semantics: a partial-filename prefix like
        ``raw/jw0123`` matches ``raw/jw0123_nrca.fits`` rather than requiring
        ``prefix`` to name an existing directory (the previous behavior, which
        silently returned nothing for a narrow prefix). Dot-prefixed hidden files
        (e.g. a partially-downloaded ``.tmp``) are excluded so an in-flight
        transfer is never surfaced as an ingestable key.
        """
        # Walk from the deepest real directory at/above the prefix (so a narrow
        # prefix doesn't force a full-root scan), then keep only files whose
        # root-relative path string actually starts with the prefix.
        search_base = self._root / prefix
        if not search_base.is_dir():
            search_base = search_base.parent
        if not search_base.is_dir():
            return []
        keys: list[str] = []
        for path in search_base.rglob("*"):
            if not path.is_file() or path.name.startswith("."):
                continue
            rel = str(path.relative_to(self._root))
            if rel.startswith(prefix):
                keys.append(rel)
        return sorted(keys)


def get_storage_service(config: Settings = settings) -> StorageBackend:
    """Return the configured storage backend: `S3StorageService` or `LocalStorageService`."""
    if config.storage_backend == "local":
        return LocalStorageService(config)
    return S3StorageService(config)


def _resolve_mc_canonical_target(config: Settings, canonical_prefix: str) -> str:
    """Return the ``mc`` target path for the canonical store, registering an S3 alias if needed.

    For the ``local`` backend the canonical store is a filesystem path under
    ``LOCAL_STORAGE_ROOT``; for S3/MinIO it is ``<alias>/<bucket>/<prefix>`` after
    an idempotent ``mc alias set`` against the configured endpoint/credentials.
    """
    if config.storage_backend == "local":
        return str(Path(config.local_storage_root) / canonical_prefix)
    subprocess.run(
        [
            "mc",
            "alias",
            "set",
            _MC_CANONICAL_ALIAS,
            config.s3_endpoint_url,
            config.aws_access_key_id,
            config.aws_secret_access_key,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    target = f"{_MC_CANONICAL_ALIAS}/{config.s3_bucket_name}"
    return f"{target}/{canonical_prefix}" if canonical_prefix else target


def sync_staging_to_canonical(
    staging_location: str, canonical_prefix: str, config: Settings = settings
) -> None:
    """Mirror new/changed files from a staging location into the canonical bucket via ``mc mirror``.

    Consumes ``mc mirror``'s ``--json`` per-file event stream line by line, logging
    one structured record per copied object — never ``subprocess.run(capture_output=True)``,
    which would buffer the entire transfer in memory before any progress is visible.
    ``mc mirror`` is itself diff-based and idempotent, so a redelivered Celery retry
    after a worker crash simply skips whatever was already copied.

    ``mc``'s real ``--json`` stream (confirmed against a live MinIO instance with
    real FITS files, not assumed) emits three distinct shapes: a per-file success
    event (``target``/``source``/``size``/``totalCount``/``totalSize`` — the latter
    two are cumulative running totals across the whole mirror, giving real
    progress even though there's no intra-file byte-level percentage); a per-file
    or whole-job error event (``status: "error"``, an ``error`` object, no
    ``target``); and a single trailing job-summary event with no ``target``/
    ``source`` at all (``total``/``transferred``/``duration``/``speed``). These are
    discriminated explicitly below rather than treating every parsed line as a
    file copy.
    """
    log = get_logger()
    canonical_target = _resolve_mc_canonical_target(config, canonical_prefix)
    log.info(
        "staging_sync_started",
        staging_location=staging_location,
        canonical_target=canonical_target,
    )

    # `--json` before the subcommand: mc emits one JSON object per transferred
    # object on stdout. stderr is folded into stdout so a failure diagnostic is
    # captured in the same stream we already read incrementally.
    process = subprocess.Popen(
        ["mc", "--json", "mirror", staging_location, canonical_target],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    copied = 0
    assert process.stdout is not None
    try:
        for line in process.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                log.warning("staging_sync_unparsed_line", line=line)
                continue

            target = event.get("target")
            if target is not None and event.get("status") != "error":
                # Real per-file success event.
                copied += 1
                log.info(
                    "staging_sync_file_copied",
                    key=target,
                    size=event.get("size"),
                    index=copied,
                    total_count=event.get("totalCount"),
                    total_size=event.get("totalSize"),
                )
            elif event.get("status") == "error":
                # Either a per-file error (target present) or a whole-job error
                # (target absent, e.g. the destination bucket doesn't exist).
                log.warning(
                    "staging_sync_file_error",
                    key=target,
                    source=event.get("source"),
                    error=event.get("error"),
                )
            else:
                # The trailing job-summary event: no target/source at all.
                log.info(
                    "staging_sync_job_summary",
                    total_bytes=event.get("total"),
                    transferred_bytes=event.get("transferred"),
                    duration_ns=event.get("duration"),
                    speed_bytes_per_sec=event.get("speed"),
                )
        return_code = process.wait()
    except SoftTimeLimitExceeded:
        # A genuine hang (network partition mid-transfer, not a clean crash) —
        # kill the subprocess so it doesn't outlive the task as an orphan, then
        # let Celery's own timeout failure handling (on_failure + DLQ) proceed.
        log.error("staging_sync_timed_out", files_copied_before_timeout=copied)
        process.kill()
        process.wait()
        raise
    if return_code != 0:
        raise RuntimeError(f"mc mirror exited with code {return_code}")
    log.info(
        "staging_sync_completed", files_copied=copied, canonical_target=canonical_target
    )


def dispatch_staging_sync(staging_location: str, canonical_prefix: str) -> str:
    """Dispatch the staging→canonical sync Celery task and return its job id.

    The shared entry point for both the API route and the CLI command — neither
    boundary runs ``mc`` in-process; the worker (where the ``mc`` binary lives)
    does. Returns the Celery task id.
    """
    from src.worker.tasks import run_staging_sync  # lazy: avoids a circular import

    async_result = run_staging_sync.delay(staging_location, canonical_prefix)
    get_logger().info(
        "staging_sync_dispatched",
        job_id=async_result.id,
        staging_location=staging_location,
        canonical_prefix=canonical_prefix,
    )
    return async_result.id
