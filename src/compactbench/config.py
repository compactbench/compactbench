"""Environment-driven runtime settings."""

from __future__ import annotations

from pathlib import Path

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


def default_benchmarks_dir() -> Path:
    """Locate the public benchmarks directory for CLI defaults.

    Resolution order:

    1. ``./benchmarks/public`` relative to the current working directory, so
       developers running CLI commands from the repo root see their local edits
       immediately.
    2. ``<installed-package>/_data/benchmarks/public`` if the wheel bundled the
       public suites (the normal path for anyone who ``pip install``-ed
       compactbench without cloning the repo).
    3. ``./benchmarks/public`` as a last resort so the CLI's existing
       "no benchmarks directory" error points at a sensible path.

    The CLI's own ``--benchmarks-dir`` flag takes precedence over all of these;
    this function only supplies the default when the flag isn't passed.
    """
    cwd_path = Path("benchmarks/public")
    if cwd_path.is_dir():
        return cwd_path

    package_root = Path(__file__).resolve().parent
    bundled = package_root / "_data" / "benchmarks" / "public"
    if bundled.is_dir():
        return bundled

    return cwd_path
