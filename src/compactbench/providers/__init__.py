"""Model provider abstractions and concrete clients.

The mock provider ships in WO-005; real providers (Groq, Google AI Studio,
Ollama) land in WO-006.
"""

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
from compactbench.providers.mock import MockProvider

_REGISTRY: dict[str, type[Provider]] = {
    MockProvider.key: MockProvider,
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
    "MockProvider",
    "Provider",
    "ProviderError",
    "ProviderResponseError",
    "UnknownProviderError",
    "get_provider_cls",
    "list_providers",
]
