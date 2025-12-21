"""Application configuration using Pydantic Settings."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"),  # Check parent dir first, then current
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application
    app_name: str = "Arquivo da Violência API"
    app_version: str = "1.0.0"
    debug: bool = False
    
    # API
    api_prefix: str = "/api"
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    # Database
    database_url: str = "sqlite+aiosqlite:///./instance/violence.db"
    
    # Redis (for ARQ task queue)
    redis_url: str = "redis://localhost:6379"
    
    # LLM (Gemini)
    gemini_api_key: str | None = None
    extraction_model: str = "gemini-2.5-flash"
    selection_model: str = "gemini-2.0-flash-lite"  # Lightweight model for classification
    
    # Pipeline settings
    pipeline_max_workers: int = 10
    pipeline_batch_size: int = 50
    
    # Telegram notifications
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None

    @property
    def database_path(self) -> Path:
        """Extract the database file path from the URL."""
        # Handle sqlite+aiosqlite:///./instance/violence.db format
        path_str = self.database_url.replace("sqlite+aiosqlite:///", "")
        return Path(path_str)


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()

