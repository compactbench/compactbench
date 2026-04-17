"""Model provider ABC.

Concrete implementations live next to this file (Groq, Google AI Studio,
Ollama, mock). Each provider normalizes request/response shapes so the runner
can swap models with a config change.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CompletionRequest:
    model: str
    prompt: str
    system: str | None = None
    max_tokens: int = 2048
    temperature: float = 0.0
    response_format: dict[str, Any] | None = None


@dataclass(frozen=True)
class CompletionResponse:
    text: str
    prompt_tokens: int
    completion_tokens: int
    model: str
    raw: dict[str, Any]


class Provider(ABC):
    key: str

    @abstractmethod
    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        """Issue a completion request and return a normalized response."""
