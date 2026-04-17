"""Model provider ABC and request/response shapes.

Concrete implementations (Groq, Google AI Studio, Ollama) live in WO-006.
The mock provider below is part of WO-005 so compactors can be tested offline.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar


@dataclass(frozen=True)
class CompletionRequest:
    """A normalized request passed to a provider's ``complete`` method."""

    model: str
    prompt: str
    system: str | None = None
    max_tokens: int = 2048
    temperature: float = 0.0
    response_format: dict[str, Any] | None = None


@dataclass(frozen=True)
class CompletionResponse:
    """A normalized response returned from a provider."""

    text: str
    prompt_tokens: int
    completion_tokens: int
    model: str
    raw: dict[str, Any] = field(default_factory=dict[str, Any])


class Provider(ABC):
    """Base class every provider must implement."""

    key: ClassVar[str]

    @abstractmethod
    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        """Issue a completion request and return a normalized response."""
