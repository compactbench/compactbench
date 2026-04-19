"""Provider wrapper that tallies token usage across every completion call.

Wrap an existing provider with :class:`CountingProvider` to get cost-relevant
telemetry for a run without changing any call sites: the wrapper forwards every
``complete`` to its inner provider and simply adds a tallying side-effect. The
current total is exposed via :meth:`snapshot` and callers can zero the
accumulator with :meth:`reset` to measure a discrete phase (e.g. one drift
cycle) in isolation.

Concurrency: the underlying I/O call runs *outside* the lock, so concurrent
callers still get full provider throughput. The lock only serializes the tiny
accumulator update, which matters when the runner fans multiple cases out
under :class:`asyncio.Semaphore`.
"""

from __future__ import annotations

import asyncio
from typing import Any, ClassVar

from compactbench.contracts import TokenUsage
from compactbench.providers.base import (
    CompletionRequest,
    CompletionResponse,
    Provider,
)


def _extract_cached_tokens(raw: dict[str, Any]) -> int:
    """Best-effort extraction of cached prompt tokens from a provider ``raw`` payload.

    Each provider names cache hits differently:

    - Anthropic: ``cache_read_input_tokens``
    - OpenAI:    ``cached_tokens``
    - Others:    no key, falls through to 0.

    Returning 0 is always safe; it just means the wrapper cannot tell cached
    from uncached prompt tokens for that provider. ``prompt_tokens`` remains
    accurate regardless.
    """
    for key in ("cache_read_input_tokens", "cached_tokens", "cache_read_tokens"):
        val = raw.get(key)
        if isinstance(val, int) and val >= 0:
            return val
    return 0


class CountingProvider(Provider):
    """Wraps another provider and accumulates a :class:`TokenUsage` across calls."""

    key: ClassVar[str] = "counting"

    def __init__(self, wrapped: Provider) -> None:
        self._wrapped = wrapped
        self._prompt_tokens = 0
        self._completion_tokens = 0
        self._cached_prompt_tokens = 0
        self._call_count = 0
        self._lock = asyncio.Lock()

    @property
    def wrapped(self) -> Provider:
        """Return the underlying provider this wrapper forwards to."""
        return self._wrapped

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        response = await self._wrapped.complete(request)
        async with self._lock:
            self._prompt_tokens += max(0, response.prompt_tokens)
            self._completion_tokens += max(0, response.completion_tokens)
            self._cached_prompt_tokens += _extract_cached_tokens(response.raw)
            self._call_count += 1
        return response

    async def snapshot(self) -> TokenUsage:
        """Return a :class:`TokenUsage` of everything seen so far (non-destructive)."""
        async with self._lock:
            return TokenUsage(
                prompt_tokens=self._prompt_tokens,
                completion_tokens=self._completion_tokens,
                cached_prompt_tokens=self._cached_prompt_tokens,
                call_count=self._call_count,
            )

    async def reset(self) -> TokenUsage:
        """Return the current totals and zero the accumulator atomically."""
        async with self._lock:
            snapshot = TokenUsage(
                prompt_tokens=self._prompt_tokens,
                completion_tokens=self._completion_tokens,
                cached_prompt_tokens=self._cached_prompt_tokens,
                call_count=self._call_count,
            )
            self._prompt_tokens = 0
            self._completion_tokens = 0
            self._cached_prompt_tokens = 0
            self._call_count = 0
            return snapshot
