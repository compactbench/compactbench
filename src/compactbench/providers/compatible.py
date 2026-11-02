"""Hosted OpenAI-compatible providers: OpenRouter, DeepSeek, Mistral, Together, Fireworks,
xAI and Gemini.

Each is the OpenAI client pointed at the host's own endpoint, with its own key variable
(``COMPACTBENCH_<NAME>_API_KEY``) and an optional base-URL override
(``COMPACTBENCH_<NAME>_BASE_URL``), which ranked evaluation uses to route calls through
its proxy. OpenRouter alone reaches hundreds of models.

Reasoning effort is passed in each host's own shape, or dropped where a host has none,
so the same method config works everywhere.
"""

from __future__ import annotations

import os
from typing import Any, ClassVar

from compactbench.providers.errors import ProviderError
from compactbench.providers.openai import OpenAIProvider


class HostedCompatibleProvider(OpenAIProvider):
    """An OpenAI-compatible host with a fixed default endpoint."""

    default_base_url: ClassVar[str]
    env_name: ClassVar[str]
    effort_style: ClassVar[str] = "none"
    """``"openai"`` (``reasoning_effort``), ``"openrouter"`` (``reasoning.effort``) or ``"none"``."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        max_retries: int = 3,
        base_backoff_seconds: float = 2.0,
    ) -> None:
        override = base_url or os.environ.get(f"COMPACTBENCH_{self.env_name}_BASE_URL") or None
        resolved_key = api_key or os.environ.get(f"COMPACTBENCH_{self.env_name}_API_KEY")
        if not resolved_key:
            raise ProviderError(
                f"{self.key} API key required. Set COMPACTBENCH_{self.env_name}_API_KEY "
                "or pass api_key=."
            )
        super().__init__(
            api_key=resolved_key,
            base_url=override or self.default_base_url,
            max_retries=max_retries,
            base_backoff_seconds=base_backoff_seconds,
        )
        self._overridden = override is not None

    @property
    def endpoint_kind(self) -> str:
        return "custom" if self._overridden else "default"

    def _effort_kwargs(self, effort: str) -> dict[str, Any]:
        if self.effort_style == "openai":
            return {"reasoning_effort": effort}
        if self.effort_style == "openrouter":
            return {"extra_body": {"reasoning": {"effort": effort}}}
        return {}


class OpenRouterProvider(HostedCompatibleProvider):
    key: ClassVar[str] = "openrouter"
    default_base_url: ClassVar[str] = "https://openrouter.ai/api/v1"
    env_name: ClassVar[str] = "OPENROUTER"
    effort_style: ClassVar[str] = "openrouter"


class DeepSeekProvider(HostedCompatibleProvider):
    key: ClassVar[str] = "deepseek"
    default_base_url: ClassVar[str] = "https://api.deepseek.com/v1"
    env_name: ClassVar[str] = "DEEPSEEK"


class MistralProvider(HostedCompatibleProvider):
    key: ClassVar[str] = "mistral"
    default_base_url: ClassVar[str] = "https://api.mistral.ai/v1"
    env_name: ClassVar[str] = "MISTRAL"


class TogetherProvider(HostedCompatibleProvider):
    key: ClassVar[str] = "together"
    default_base_url: ClassVar[str] = "https://api.together.xyz/v1"
    env_name: ClassVar[str] = "TOGETHER"


class FireworksProvider(HostedCompatibleProvider):
    key: ClassVar[str] = "fireworks"
    default_base_url: ClassVar[str] = "https://api.fireworks.ai/inference/v1"
    env_name: ClassVar[str] = "FIREWORKS"


class XAIProvider(HostedCompatibleProvider):
    key: ClassVar[str] = "xai"
    default_base_url: ClassVar[str] = "https://api.x.ai/v1"
    env_name: ClassVar[str] = "XAI"
    effort_style: ClassVar[str] = "openai"


class GeminiProvider(HostedCompatibleProvider):
    """Gemini through Google's OpenAI-compatible endpoint (``google-ai-studio`` uses the native SDK)."""

    key: ClassVar[str] = "gemini"
    default_base_url: ClassVar[str] = "https://generativelanguage.googleapis.com/v1beta/openai"
    env_name: ClassVar[str] = "GEMINI"
    effort_style: ClassVar[str] = "openai"


HOSTED_PROVIDERS: tuple[type[HostedCompatibleProvider], ...] = (
    OpenRouterProvider,
    DeepSeekProvider,
    MistralProvider,
    TogetherProvider,
    FireworksProvider,
    XAIProvider,
    GeminiProvider,
)
