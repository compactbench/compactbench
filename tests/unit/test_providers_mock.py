"""Mock provider tests."""

from __future__ import annotations

import pytest

from compactbench.providers import (
    CompletionRequest,
    MockProvider,
    UnknownProviderError,
    get_provider_cls,
    list_providers,
)

pytestmark = pytest.mark.unit


async def test_default_empty_response() -> None:
    mock = MockProvider()
    resp = await mock.complete(CompletionRequest(model="any", prompt="hi"))
    assert resp.text == ""
    assert resp.model == "any"


async def test_scripted_sequence_consumed_in_order() -> None:
    mock = MockProvider(responses=["first", "second", "third"])
    results: list[str] = []
    for _ in range(3):
        resp = await mock.complete(CompletionRequest(model="m", prompt="p"))
        results.append(resp.text)
    assert results == ["first", "second", "third"]


async def test_after_sequence_exhausted_returns_default() -> None:
    mock = MockProvider(responses=["one"], default="fallback")
    r1 = await mock.complete(CompletionRequest(model="m", prompt="p"))
    r2 = await mock.complete(CompletionRequest(model="m", prompt="p"))
    assert r1.text == "one"
    assert r2.text == "fallback"


async def test_records_calls() -> None:
    mock = MockProvider(default="ok")
    await mock.complete(CompletionRequest(model="a", prompt="first"))
    await mock.complete(CompletionRequest(model="b", prompt="second"))
    assert len(mock.calls) == 2
    assert mock.calls[0].prompt == "first"
    assert mock.calls[1].model == "b"


async def test_reset_clears_calls_and_rewinds_sequence() -> None:
    mock = MockProvider(responses=["one", "two"])
    await mock.complete(CompletionRequest(model="m", prompt="p"))
    mock.reset()
    assert mock.calls == []
    resp = await mock.complete(CompletionRequest(model="m", prompt="p"))
    assert resp.text == "one"


async def test_response_token_counts_are_positive() -> None:
    mock = MockProvider(default="hello world")
    resp = await mock.complete(CompletionRequest(model="m", prompt="some prompt text"))
    assert resp.prompt_tokens >= 1
    assert resp.completion_tokens >= 1


def test_list_providers_includes_mock() -> None:
    assert "mock" in list_providers()


def test_get_provider_cls_returns_class() -> None:
    cls = get_provider_cls("mock")
    assert cls is MockProvider


def test_get_provider_cls_raises_on_unknown() -> None:
    with pytest.raises(UnknownProviderError):
        get_provider_cls("not-a-real-provider")
