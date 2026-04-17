"""Retry-helper tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from compactbench.providers._retry import retry_with_backoff

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
