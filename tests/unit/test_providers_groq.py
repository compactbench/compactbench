"""Groq provider tests (SDK mocked)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from groq import APITimeoutError, RateLimitError

from compactbench.providers import (
    CompletionRequest,
    GroqProvider,
    ProviderError,
    ProviderResponseError,
)

pytestmark = pytest.mark.unit


def _ok_response(text: str = "the answer", model: str = "llama-test") -> MagicMock:
    message = MagicMock(content=text)
    choice = MagicMock(message=message, finish_reason="stop")
    usage = MagicMock(prompt_tokens=10, completion_tokens=5)
    return MagicMock(choices=[choice], usage=usage, model=model, id="resp-id")


def _build_provider(*, max_retries: int = 3) -> GroqProvider:
    return GroqProvider(api_key="test-key", max_retries=max_retries, base_backoff_seconds=0.0)


def _mock_create(provider: GroqProvider) -> AsyncMock:
    mock = AsyncMock()
    provider._client.chat.completions.create = mock  # pyright: ignore[reportPrivateUsage]
    return mock


def _rate_limit_error() -> RateLimitError:
    return RateLimitError.__new__(RateLimitError)


def _timeout_error() -> APITimeoutError:
    return APITimeoutError.__new__(APITimeoutError)


async def test_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("COMPACTBENCH_GROQ_API_KEY", raising=False)
    with pytest.raises(ProviderError, match="Groq API key"):
        GroqProvider()


async def test_uses_env_var_when_api_key_not_passed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("COMPACTBENCH_GROQ_API_KEY", "env-key")
    provider = GroqProvider()
    assert provider is not None


async def test_complete_returns_parsed_response() -> None:
    provider = _build_provider()
    mock = _mock_create(provider)
    mock.return_value = _ok_response("hello", model="llama-3.3")

    resp = await provider.complete(CompletionRequest(model="llama-3.3", prompt="say hi"))

    assert resp.text == "hello"
    assert resp.prompt_tokens == 10
    assert resp.completion_tokens == 5
    assert resp.model == "llama-3.3"
    assert resp.raw["provider"] == "groq"
    assert resp.raw["finish_reason"] == "stop"


async def test_complete_forwards_request_parameters() -> None:
    provider = _build_provider()
    mock = _mock_create(provider)
    mock.return_value = _ok_response()

    await provider.complete(
        CompletionRequest(
            model="m",
            prompt="p",
            system="sys",
            max_tokens=123,
            temperature=0.2,
            response_format={"type": "json_object"},
        )
    )

    assert mock.await_args is not None
    kwargs = mock.await_args.kwargs
    assert kwargs["model"] == "m"
    assert kwargs["max_tokens"] == 123
    assert kwargs["temperature"] == 0.2
    assert kwargs["response_format"] == {"type": "json_object"}
    assert kwargs["messages"] == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "p"},
    ]


async def test_omits_response_format_when_not_requested() -> None:
    provider = _build_provider()
    mock = _mock_create(provider)
    mock.return_value = _ok_response()

    await provider.complete(CompletionRequest(model="m", prompt="p"))
    assert mock.await_args is not None
    assert "response_format" not in mock.await_args.kwargs


async def test_retries_on_rate_limit_then_succeeds() -> None:
    provider = _build_provider(max_retries=3)
    mock = _mock_create(provider)
    mock.side_effect = [_rate_limit_error(), _rate_limit_error(), _ok_response("ok")]

    resp = await provider.complete(CompletionRequest(model="m", prompt="p"))
    assert resp.text == "ok"
    assert mock.await_count == 3


async def test_retries_on_timeout() -> None:
    provider = _build_provider(max_retries=2)
    mock = _mock_create(provider)
    mock.side_effect = [_timeout_error(), _ok_response()]

    resp = await provider.complete(CompletionRequest(model="m", prompt="p"))
    assert resp is not None
    assert mock.await_count == 2


async def test_gives_up_after_max_retries_on_rate_limit() -> None:
    provider = _build_provider(max_retries=2)
    mock = _mock_create(provider)
    mock.side_effect = [_rate_limit_error(), _rate_limit_error()]

    with pytest.raises(RateLimitError):
        await provider.complete(CompletionRequest(model="m", prompt="p"))
    assert mock.await_count == 2


async def test_raises_on_empty_choices() -> None:
    provider = _build_provider()
    mock = _mock_create(provider)
    mock.return_value = MagicMock(choices=[], usage=None, model="m", id="id")

    with pytest.raises(ProviderResponseError, match="no choices"):
        await provider.complete(CompletionRequest(model="m", prompt="p"))


async def test_handles_missing_usage() -> None:
    provider = _build_provider()
    mock = _mock_create(provider)
    response = _ok_response()
    response.usage = None
    mock.return_value = response

    resp = await provider.complete(CompletionRequest(model="m", prompt="p"))
    assert resp.prompt_tokens == 0
    assert resp.completion_tokens == 0


async def test_cached_prefix_is_concatenated_into_user_content() -> None:
    """Groq doesn't advertise caching; behaviour is equivalent to a single call."""
    provider = _build_provider()
    mock = _mock_create(provider)
    mock.return_value = _ok_response()

    await provider.complete(
        CompletionRequest(
            model="m",
            prompt="suffix",
            cached_prefix="PREFIX ",
        )
    )
    assert mock.await_args is not None
    assert mock.await_args.kwargs["messages"][-1]["content"] == "PREFIX suffix"
