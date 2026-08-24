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
    """A normalized request passed to a provider's ``complete`` method.

    ``cached_prefix`` is an optimisation hint. When set, the effective user
    input is ``cached_prefix + prompt`` and the provider is free to cache the
    prefix to avoid re-billing the input tokens on subsequent calls that reuse
    it verbatim. Semantics:

    - **Anthropic** wraps the prefix in an explicit ``cache_control: ephemeral``
      content block, which drops the cached tokens' input cost by ~90% on hits.
    - **OpenAI** simply prepends the prefix; OpenAI's automatic prompt caching
      picks up any stable prefix ≥ 1024 tokens at the start of a message.
    - **Groq / Ollama / Gemini / Mock** currently just prepend and make a
      regular call. Providers MAY add caching semantics later without changing
      the call site.

    When ``cached_prefix`` is ``None`` every provider behaves exactly as it
    did before this field existed.
    """

    model: str
    prompt: str
    system: str | None = None
    max_tokens: int = 2048
    temperature: float = 0.0
    response_format: dict[str, Any] | None = None
    cached_prefix: str | None = None


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

    @property
    def endpoint_kind(self) -> str:
        """``"default"`` or ``"custom"`` — where this provider's calls actually go.

        The leaderboard ranks within ``(benchmark_version, target_provider,
        target_model, scorer_version)`` segments so that methods evaluated
        against different models never compete numerically. ``target_provider``
        and ``target_model`` are both caller-supplied strings, so without this
        signal a locally-served model submitted as ``--provider openai --model
        gpt-4o`` lands in the segment for *genuine* gpt-4o and is ranked against
        it. That is a comparability failure, which is the one thing a
        leaderboard cannot afford.

        Providers that can be pointed somewhere other than their vendor default
        override this. Deliberately coarse: the URL itself is frequently an
        internal host and ``results.jsonl`` files get shared, so only the fact
        that the endpoint differed is recorded, never the value.
        """
        return "default"
