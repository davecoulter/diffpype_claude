"""Type-safe application configuration sourced from environment variables / .env."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Validated application settings, separate from raw Docker infrastructure env vars."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

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


settings = Settings()
"""Module-level singleton so every component shares one validated configuration."""
