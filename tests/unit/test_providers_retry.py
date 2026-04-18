"""Retry-helper tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from compactbench.providers._retry import is_terminal_quota_error, retry_with_backoff

pytestmark = pytest.mark.unit


class _TransientError(Exception):
    """Simulates a retryable condition."""


class _PermanentError(Exception):
    """Simulates a non-retryable condition."""


async def test_returns_on_first_success() -> None:
    op = AsyncMock(return_value="ok")
    result = await retry_with_backoff(
        op,
        is_retryable=lambda _exc: True,
        max_retries=3,
        base_delay=0.0,
    )
    assert result == "ok"
    assert op.await_count == 1


async def test_retries_then_succeeds() -> None:
    op = AsyncMock(side_effect=[_TransientError("1"), _TransientError("2"), "ok"])
    result = await retry_with_backoff(
        op,
        is_retryable=lambda exc: isinstance(exc, _TransientError),
        max_retries=3,
        base_delay=0.0,
    )
    assert result == "ok"
    assert op.await_count == 3


async def test_reraises_non_retryable_immediately() -> None:
    op = AsyncMock(side_effect=_PermanentError("nope"))
    with pytest.raises(_PermanentError):
        await retry_with_backoff(
            op,
            is_retryable=lambda exc: isinstance(exc, _TransientError),
            max_retries=3,
            base_delay=0.0,
        )
    assert op.await_count == 1


async def test_gives_up_after_max_retries() -> None:
    op = AsyncMock(side_effect=_TransientError("always-fails"))
    with pytest.raises(_TransientError, match="always-fails"):
        await retry_with_backoff(
            op,
            is_retryable=lambda exc: isinstance(exc, _TransientError),
            max_retries=3,
            base_delay=0.0,
        )
    assert op.await_count == 3


async def test_delay_grows_exponentially() -> None:
    op = AsyncMock(side_effect=[_TransientError("1"), _TransientError("2"), "ok"])
    with patch("compactbench.providers._retry.asyncio.sleep", new=AsyncMock()) as sleep_mock:
        await retry_with_backoff(
            op,
            is_retryable=lambda _exc: True,
            max_retries=3,
            base_delay=1.0,
            max_delay=10.0,
        )
    delays = [call.args[0] for call in sleep_mock.await_args_list]
    assert delays == [1.0, 2.0]


async def test_delay_capped_by_max_delay() -> None:
    op = AsyncMock(
        side_effect=[_TransientError("1"), _TransientError("2"), _TransientError("3"), "ok"]
    )
    with patch("compactbench.providers._retry.asyncio.sleep", new=AsyncMock()) as sleep_mock:
        await retry_with_backoff(
            op,
            is_retryable=lambda _exc: True,
            max_retries=4,
            base_delay=1.0,
            max_delay=2.0,
        )
    delays = [call.args[0] for call in sleep_mock.await_args_list]
    assert delays == [1.0, 2.0, 2.0]


async def test_invalid_max_retries_raises() -> None:
    with pytest.raises(ValueError, match=">= 1"):
        await retry_with_backoff(
            AsyncMock(return_value="ok"),
            is_retryable=lambda _exc: True,
            max_retries=0,
        )


class TestIsTerminalQuotaError:
    """Covers the daily/monthly-quota detection heuristic used by every provider."""

    def test_detects_groq_tokens_per_day_message(self) -> None:
        exc = Exception(
            "Error code: 429 - {'error': {'message': 'Rate limit reached for model "
            "llama-3.3-70b-versatile ... service tier on_demand on tokens per day (TPD): "
            "Limit 100000, Used 99579. Please try again in 1m4.8s.'}}"
        )
        assert is_terminal_quota_error(exc)

    def test_detects_openai_insufficient_quota(self) -> None:
        exc = Exception("insufficient_quota: You have exceeded your monthly limit.")
        assert is_terminal_quota_error(exc)

    def test_detects_daily_limit_prose(self) -> None:
        assert is_terminal_quota_error(Exception("Hit daily limit, retry tomorrow"))

    def test_detects_rpd_marker(self) -> None:
        assert is_terminal_quota_error(Exception("requests per day (RPD) exceeded"))

    def test_rejects_per_minute_rate_limit(self) -> None:
        """Per-minute / per-second 429s should retry; they clear in our window."""
        exc = Exception("Rate limit reached: requests per minute. Retry after 2s.")
        assert not is_terminal_quota_error(exc)

    def test_rejects_generic_transient_error(self) -> None:
        assert not is_terminal_quota_error(Exception("connection reset"))
        assert not is_terminal_quota_error(Exception("Internal server error"))

    def test_case_insensitive(self) -> None:
        """Providers capitalise inconsistently; our matcher should not care."""
        assert is_terminal_quota_error(Exception("TOKENS PER DAY exceeded"))
        assert is_terminal_quota_error(Exception("Quota Exceeded"))
