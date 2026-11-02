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


#: Rate limits reset on a per-minute window, so a 429 gets more patience than
#: other transient errors.
RATE_LIMIT_RETRIES = 8
RATE_LIMIT_MAX_DELAY = 90.0


def retry_after_seconds(exc: Exception) -> float | None:
    """The server's ``retry-after`` hint on ``exc``, if it carries an HTTP response."""
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if headers is None:
        return None
    try:
        raw = headers.get("retry-after")
    except Exception:
        return None
    try:
        return float(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None


def _is_rate_limit(exc: Exception) -> bool:
    return getattr(exc, "status_code", None) == 429


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
    Rate limits (HTTP 429) get up to :data:`RATE_LIMIT_RETRIES` attempts and wait
    at least the server's ``retry-after``, up to :data:`RATE_LIMIT_MAX_DELAY`.
    After the attempts run out the last exception is re-raised. Non-retryable
    exceptions are re-raised immediately.
    """
    if max_retries < 1:
        raise ValueError(f"max_retries must be >= 1, got {max_retries}")

    attempt = 0
    while True:
        try:
            return await operation()
        except Exception as exc:
            if not is_retryable(exc):
                raise
            rate_limited = _is_rate_limit(exc)
            budget = max(max_retries, RATE_LIMIT_RETRIES) if rate_limited else max_retries
            if attempt >= budget - 1:
                raise
            ceiling = RATE_LIMIT_MAX_DELAY if rate_limited else max_delay
            delay = min(base_delay * (2**attempt), ceiling)
            hint = retry_after_seconds(exc)
            if hint is not None:
                delay = min(max(delay, hint), ceiling)
            await asyncio.sleep(delay)
            attempt += 1
