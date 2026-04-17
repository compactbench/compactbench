"""Model provider abstractions and concrete clients."""

from compactbench.providers.base import (
    CompletionRequest,
    CompletionResponse,
    Provider,
)
from compactbench.providers.errors import (
    ProviderError,
    ProviderResponseError,
    UnknownProviderError,
)
from compactbench.providers.google_ai_studio import GoogleAIStudioProvider
from compactbench.providers.groq import GroqProvider
from compactbench.providers.mock import MockProvider
from compactbench.providers.ollama import OllamaProvider

_REGISTRY: dict[str, type[Provider]] = {
    MockProvider.key: MockProvider,
    GroqProvider.key: GroqProvider,
    GoogleAIStudioProvider.key: GoogleAIStudioProvider,
    OllamaProvider.key: OllamaProvider,
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
    "CompletionRequest",
    "CompletionResponse",
    "GoogleAIStudioProvider",
    "GroqProvider",
    "MockProvider",
    "OllamaProvider",
    "Provider",
    "ProviderError",
    "ProviderResponseError",
    "UnknownProviderError",
    "get_provider_cls",
    "list_providers",
]
