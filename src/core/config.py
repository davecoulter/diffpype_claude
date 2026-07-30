"""Type-safe application configuration sourced from environment variables / .env."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Validated application settings, separate from raw Docker infrastructure env vars."""

    model_config = SettingsConfigDict(
        env_file=".env", extra="ignore", case_sensitive=False
    )

    database_url: str
    redis_url: str
    log_level: str = "INFO"
    admin_user: str = "sysadmin"
    admin_password: str = "changeme"
    admin_secret_key: str = "diffpype-dev-secret-key-change-in-production"
    cors_origins: str = "http://localhost:5173"
    celery_task_max_retries: int = 3
    celery_task_retry_delay: int = 60
    enable_db_backup_cron: bool = False
    db_pool_size: int = 20
    db_max_overflow: int = 10
    s3_endpoint_url: str = "http://minio:9000"
    aws_access_key_id: str = "minioadmin"
    aws_secret_access_key: str = "minioadmin"
    s3_bucket_name: str = "diffpype-data"
    s3_region: str = "us-east-1"
    storage_backend: str = "s3"
    local_storage_root: str = "./data"
    staging_location: str = "./data/staging"
    staging_sync_interval_seconds: int = 300
    enable_staging_sync_cron: bool = True
    staging_sync_soft_time_limit_seconds: int = 1800
    ingest_batch_soft_time_limit_seconds: int = 7200
    mosaic_drizzle_soft_time_limit_seconds: int = 3600
    cli_tool_soft_time_limit_seconds: int = 3600
    db_backup_soft_time_limit_seconds: int = 3600
    dlq_dump_soft_time_limit_seconds: int = 30
    reconcile_stuck_jobs_soft_time_limit_seconds: int = 120
    job_staleness_timeout_seconds: int = 3600


settings = Settings()  # type: ignore[call-arg]  # database_url/redis_url are populated from the environment at runtime; mypy can't see that.
"""Module-level singleton so every component shares one validated configuration."""
