"""Shared async exponential-backoff retry helper for providers.

Each provider decides which of its SDK's exceptions are retryable (typically
rate-limit and transient network errors) and hands a predicate plus the async
call to :func:`retry_with_backoff`.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

T = TypeVar("T")


# Markers that appear in provider error bodies/messages when the caller has hit
# a per-day or per-month quota that won't clear inside a retry window measured
# in seconds. Retrying these is futile and burns attempts; short-circuit them
# at the predicate layer so the caller sees the original error immediately.
_TERMINAL_QUOTA_MARKERS = (
    "tokens per day",
    "tokens_per_day",
    "requests per day",
    "requests_per_day",
    "tpd",
    "rpd",
    "daily limit",
    "daily quota",
    "monthly limit",
    "monthly quota",
    "quota exceeded",
    "insufficient_quota",
)


def is_terminal_quota_error(exc: Exception) -> bool:
    """Return True if ``exc`` signals a quota window too long to retry through.

    Works heuristically on the error's string representation because provider
    SDKs expose 429 details through inconsistent attribute shapes — Groq puts
    ``{'type': 'tokens'}`` in the body, OpenAI uses ``insufficient_quota`` /
    ``rate_limit_exceeded`` codes, Anthropic returns prose messages. Matching
    on the rendered message covers all three without SDK-specific branching.
    """
    text = str(exc).lower()
    return any(marker in text for marker in _TERMINAL_QUOTA_MARKERS)


async def retry_with_backoff(
    operation: Callable[[], Awaitable[T]],
    *,
    is_retryable: Callable[[Exception], bool],
    max_retries: int = 3,
    base_delay: float = 2.0,
    max_delay: float = 30.0,
) -> T:
    """Call ``operation`` with exponential backoff on retryable exceptions.

    Returns the operation's result on first success. On a retryable failure,
    waits ``min(base_delay * 2**attempt, max_delay)`` seconds and retries.
    After ``max_retries`` failed attempts the last exception is re-raised.
    Non-retryable exceptions are re-raised immediately.
    """
    if max_retries < 1:
        raise ValueError(f"max_retries must be >= 1, got {max_retries}")

    last_exc: Exception | None = None
    for attempt in range(max_retries):
        try:
            return await operation()
        except Exception as exc:
            if not is_retryable(exc):
                raise
            last_exc = exc
            if attempt < max_retries - 1:
                delay = min(base_delay * (2**attempt), max_delay)
                await asyncio.sleep(delay)

    assert last_exc is not None  # unreachable unless last_exc was set in the loop
    raise last_exc
