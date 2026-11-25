"""Application settings, loaded from environment variables (12-factor style)."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Rafta API"
    environment: str = "development"

    # Primary connection (read/write). SQLite works for local dev and tests.
    database_url: str = "sqlite:///./rafta.db"
    # Optional read-only connection used exclusively by the AI assistant tools.
    database_readonly_url: str | None = None

    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    # Background jobs
    scheduler_enabled: bool = True
    forecast_cron: str = "0 2 * * *"  # nightly at 02:00
    seed_on_startup: bool = False

    # Forecasting defaults
    forecast_horizon_days: int = 28
    backtest_folds: int = 3
    enable_lightgbm: bool = True

    # Inventory policy defaults (service levels per ABC class)
    service_level_a: float = 0.98
    service_level_b: float = 0.95
    service_level_c: float = 0.90
    uniform_service_level: float = 0.95

    # AI assistant: any OpenAI-compatible endpoint (Groq, Ollama, Gemini, OpenRouter...).
    llm_base_url: str | None = None
    llm_api_key: str | None = None
    llm_model: str = "llama-3.3-70b-versatile"
    llm_timeout_s: float = 30.0
    assistant_max_tool_rounds: int = 4


@lru_cache
def get_settings() -> Settings:
    return Settings()
