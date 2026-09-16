"""Application configuration loaded from environment variables."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings with sensible local defaults."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = Field(default="reconai", description="Service name")
    app_env: str = Field(default="local", description="Environment name")
    debug: bool = Field(default=True, description="Enable debug mode")
    api_prefix: str = Field(default="", description="Optional API path prefix")

    # Local default targets PostgreSQL. Override via DATABASE_URL; never commit secrets.
    database_url: str = Field(
        default="postgresql+psycopg://reconai:reconai@localhost:5432/reconai",
        description="SQLAlchemy database URL (PostgreSQL in production/local)",
    )


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()
