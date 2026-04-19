"""Model provider abstractions and concrete clients."""

from compactbench.providers.anthropic import AnthropicProvider
from compactbench.providers.base import (
    CompletionRequest,
    CompletionResponse,
    Provider,
)
from compactbench.providers.counting import CountingProvider
from compactbench.providers.errors import (
    ProviderError,
    ProviderResponseError,
    UnknownProviderError,
)
from compactbench.providers.google_ai_studio import GoogleAIStudioProvider
from compactbench.providers.groq import GroqProvider
from compactbench.providers.mock import MockProvider
from compactbench.providers.ollama import OllamaProvider
from compactbench.providers.openai import OpenAIProvider

_REGISTRY: dict[str, type[Provider]] = {
    MockProvider.key: MockProvider,
    GroqProvider.key: GroqProvider,
    GoogleAIStudioProvider.key: GoogleAIStudioProvider,
    OllamaProvider.key: OllamaProvider,
    AnthropicProvider.key: AnthropicProvider,
    OpenAIProvider.key: OpenAIProvider,
}


def list_providers() -> list[str]:
    """Return the sorted list of registered provider keys."""
    return sorted(_REGISTRY)


def get_provider_cls(key: str) -> type[Provider]:
    """Return the provider class for ``key`` or raise :class:`UnknownProviderError`."""
    cls = _REGISTRY.get(key)
    if cls is None:
        raise UnknownProviderError(f"unknown provider {key!r}. Known: {sorted(_REGISTRY)}")
    return cls


__all__ = [
    "AnthropicProvider",
    "CompletionRequest",
    "CompletionResponse",
    "CountingProvider",
    "GoogleAIStudioProvider",
    "GroqProvider",
    "MockProvider",
    "OllamaProvider",
    "OpenAIProvider",
    "Provider",
    "ProviderError",
    "ProviderResponseError",
    "UnknownProviderError",
    "get_provider_cls",
    "list_providers",
]
