"""Tests for the :class:`CountingProvider` wrapper."""

from __future__ import annotations

import asyncio

import pytest

from compactbench.providers import (
    CompletionRequest,
    CompletionResponse,
    CountingProvider,
    MockProvider,
    Provider,
)

pytestmark = pytest.mark.unit


def _req(prompt: str = "hello", cached_prefix: str | None = None) -> CompletionRequest:
    return CompletionRequest(model="m", prompt=prompt, cached_prefix=cached_prefix)


@pytest.mark.asyncio
async def test_snapshot_starts_at_zero() -> None:
    counting = CountingProvider(MockProvider(default="x"))
    snap = await counting.snapshot()
    assert snap.prompt_tokens == 0
    assert snap.completion_tokens == 0
    assert snap.cached_prompt_tokens == 0
    assert snap.call_count == 0


@pytest.mark.asyncio
async def test_accumulates_across_calls() -> None:
    inner = MockProvider(default="response-text")
    counting = CountingProvider(inner)

    await counting.complete(_req())
    await counting.complete(_req())
    await counting.complete(_req())

    snap = await counting.snapshot()
    assert snap.call_count == 3
    # Mock returns max(1, len(text) // 4) for each field — non-trivial positive values.
    assert snap.prompt_tokens > 0
    assert snap.completion_tokens > 0


@pytest.mark.asyncio
async def test_snapshot_is_non_destructive() -> None:
    counting = CountingProvider(MockProvider(default="x"))
    await counting.complete(_req())
    first = await counting.snapshot()
    second = await counting.snapshot()
    assert first == second


@pytest.mark.asyncio
async def test_reset_returns_prior_and_zeroes() -> None:
    counting = CountingProvider(MockProvider(default="x"))
    await counting.complete(_req())
    await counting.complete(_req())
    prior = await counting.reset()
    assert prior.call_count == 2
    now = await counting.snapshot()
    assert now.call_count == 0
    assert now.prompt_tokens == 0


@pytest.mark.asyncio
async def test_reset_then_accumulate_again_gives_independent_total() -> None:
    counting = CountingProvider(MockProvider(default="x"))
    await counting.complete(_req())
    first_phase = await counting.reset()
    await counting.complete(_req())
    second_phase = await counting.snapshot()
    assert first_phase.call_count == 1
    assert second_phase.call_count == 1


@pytest.mark.asyncio
async def test_forwards_response_unchanged() -> None:
    inner = MockProvider(responses=["hello world"])
    counting = CountingProvider(inner)
    response = await counting.complete(_req())
    assert response.text == "hello world"
    assert response.prompt_tokens > 0
    assert response.completion_tokens > 0


@pytest.mark.asyncio
async def test_extracts_anthropic_cache_read_tokens() -> None:
    class FakeAnthropic(Provider):
        key = "fake-anthropic"

        async def complete(self, request: CompletionRequest) -> CompletionResponse:
            return CompletionResponse(
                text="ok",
                prompt_tokens=400,
                completion_tokens=10,
                model=request.model,
                raw={"provider": "anthropic", "cache_read_input_tokens": 360},
            )

    counting = CountingProvider(FakeAnthropic())
    await counting.complete(_req())
    snap = await counting.snapshot()
    assert snap.prompt_tokens == 400
    assert snap.cached_prompt_tokens == 360


@pytest.mark.asyncio
async def test_extracts_openai_cached_tokens() -> None:
    class FakeOpenAI(Provider):
        key = "fake-openai"

        async def complete(self, request: CompletionRequest) -> CompletionResponse:
            return CompletionResponse(
                text="ok",
                prompt_tokens=500,
                completion_tokens=20,
                model=request.model,
                raw={"provider": "openai", "cached_tokens": 200},
            )

    counting = CountingProvider(FakeOpenAI())
    await counting.complete(_req())
    snap = await counting.snapshot()
    assert snap.cached_prompt_tokens == 200


@pytest.mark.asyncio
async def test_zero_cache_on_providers_without_telemetry() -> None:
    counting = CountingProvider(MockProvider(default="x"))
    await counting.complete(_req())
    snap = await counting.snapshot()
    assert snap.cached_prompt_tokens == 0


@pytest.mark.asyncio
async def test_concurrent_calls_are_all_counted() -> None:
    counting = CountingProvider(MockProvider(default="x"))
    await asyncio.gather(*(counting.complete(_req()) for _ in range(50)))
    snap = await counting.snapshot()
    assert snap.call_count == 50


@pytest.mark.asyncio
async def test_wrapped_accessor_returns_underlying_provider() -> None:
    inner = MockProvider(default="x")
    counting = CountingProvider(inner)
    assert counting.wrapped is inner
