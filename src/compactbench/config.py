"""Environment-driven runtime settings."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Global settings read from environment variables and ``.env``."""

    model_config = SettingsConfigDict(
        env_prefix="COMPACTBENCH_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Providers
    groq_api_key: str | None = Field(default=None)
    google_ai_studio_api_key: str | None = Field(default=None)
    ollama_base_url: str = Field(default="http://localhost:11434")

    # Evaluation defaults
    default_drift_cycles: int = Field(default=2, ge=0, le=5)
    default_provider: str = Field(default="mock")
    default_model: str = Field(default="mock-deterministic")

    # Determinism
    tokenizer: str = Field(default="cl100k_base")

    # Paths
    results_dir: str = Field(default="results")


settings = Settings()
