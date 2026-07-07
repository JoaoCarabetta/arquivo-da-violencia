"""Application configuration using Pydantic Settings."""

from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

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
    environment: str = "development"
    
    # API
    api_prefix: str = "/api"
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://localhost:3000",
        "https://arquivodaviolencia.com.br",
        "https://www.arquivodaviolencia.com.br",
    ]

    # Database
    database_url: str = "sqlite+aiosqlite:///./instance/violence.db"
    db_pool_size: int = 30
    db_pool_overflow: int = 70
    
    # Redis (for ARQ task queue)
    redis_url: str = "redis://localhost:6379"
    
    # LLM (via OpenRouter) - per-stage models validated by the eval harness (backend/eval/)
    # Model slugs are OpenRouter IDs: "<vendor>/<model>".
    openrouter_api_key: str | None = None
    extraction_model: str = "deepseek/deepseek-v4-flash"  # Structured event extraction
    selection_model: str = "openai/gpt-oss-120b"  # Headline classification
    content_gate_model: str = "google/gemini-2.5-flash-lite"  # Article-body content gate
    dedup_model: str = "google/gemini-3.1-flash-lite"  # Dedup match + cluster
    enrichment_model: str = "deepseek/deepseek-v4-flash"  # Multi-source synthesis

    # Google Maps Geocoding (optional - geocoding no-ops when unset)
    google_maps_api_key: str | None = None
    
    # Pipeline settings
    pipeline_max_workers: int = 10
    pipeline_batch_size: int = 50

    # Download settings
    download_timeout_seconds: float = 20.0
    # Browser-like User-Agent so anti-bot sites don't reject the fetch outright.
    download_user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )

    # Extraction settings
    # Truncate article content before sending to the LLM to avoid context-window
    # / token-limit failures on very long pages.
    extraction_max_chars: int = 32000
    # Cap on the LLM's OUTPUT tokens. The extraction schema is large, so the
    # default provider cap can truncate the response (finish_reason="length"),
    # surfacing as IncompleteOutputException. Raise it to give the model room.
    extraction_max_output_tokens: int = 16384

    # Retry of transient pipeline failures
    pipeline_max_attempts: int = 3
    
    # Telegram notifications
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None
    
    # GitHub issue creation on failures
    github_token: str | None = None
    github_repo: str | None = None  # Format: "owner/repo"

    hetzner_api_token: str | None = None

    grafana_cloud_prom_url: str | None = None
    grafana_cloud_prom_user: str | None = None
    grafana_cloud_prom_key: str | None = None
    grafana_cloud_loki_url: str | None = None
    grafana_cloud_loki_user: str | None = None
    grafana_cloud_loki_key: str | None = None
    metrics_push_interval_seconds: int = 30
    metrics_enabled: bool = True

    @property
    def is_sqlite(self) -> bool:
        """True when the configured database URL targets SQLite."""
        return "sqlite" in self.database_url.lower()

    @property
    def database_path(self) -> Path:
        """Extract the SQLite database file path from the URL."""
        if not self.is_sqlite:
            raise ValueError("database_path is only available for SQLite URLs")
        path_str = self.database_url.replace("sqlite+aiosqlite:///", "")
        path_str = path_str.replace("sqlite:///", "")
        return Path(path_str)

    @property
    def database_display_name(self) -> str:
        """Human-readable database target for logs (password redacted)."""
        if self.is_sqlite:
            return str(self.database_path)
        parsed = urlparse(self.database_url)
        host = parsed.hostname or "localhost"
        port = f":{parsed.port}" if parsed.port else ""
        db_name = (parsed.path or "").lstrip("/") or "postgres"
        return f"{host}{port}/{db_name}"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
