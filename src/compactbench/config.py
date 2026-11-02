"""Environment-driven runtime settings."""

from __future__ import annotations

import os
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


def load_dotenv(path: Path | None = None) -> dict[str, str]:
    """Load ``COMPACTBENCH_*`` variables from a ``.env`` file into ``os.environ``.

    Every provider reads ``os.environ`` directly at construction, so the
    ``Settings`` object above never reached them — ``.env`` was documented as
    the way to supply API keys and silently did nothing. Rather than drop a
    genuinely useful feature, populate the environment before providers are
    built so the documented path works for all of them at once.

    Precedence: a variable already present in the real environment always wins,
    matching how every other dotenv implementation behaves — an explicit
    ``export`` should not be overridden by a checked-in file.

    Only ``COMPACTBENCH_``-prefixed names are read. A ``.env`` frequently holds
    unrelated secrets, and this should not import them into the process.

    Returns the mapping it actually applied, for logging and tests.
    """
    env_path = path if path is not None else Path(".env")
    if not env_path.is_file():
        return {}

    applied: dict[str, str] = {}
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        # `export FOO=bar` is common in hand-written .env files.
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        name, _, value = line.partition("=")
        name = name.strip()
        if not name.startswith("COMPACTBENCH_"):
            continue
        value = value.strip()
        # Strip one matched pair of surrounding quotes, if present.
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        if name in os.environ:
            continue
        os.environ[name] = value
        applied[name] = value
    return applied
