"""Type-safe application configuration sourced from environment variables / .env."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Validated application settings, separate from raw Docker infrastructure env vars."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    database_url: str
    redis_url: str
    log_level: str = "INFO"


settings = Settings()
"""Module-level singleton so every component shares one validated configuration."""
