"""OpenAI provider tests (SDK mocked)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from openai import APITimeoutError, InternalServerError, RateLimitError

from compactbench.providers import (
    CompletionRequest,
    OpenAIProvider,
    ProviderError,
    ProviderResponseError,
)

pytestmark = pytest.mark.unit


def _ok_response(text: str = "the answer", model: str = "gpt-4o-mini") -> MagicMock:
    message = MagicMock(content=text)
    choice = MagicMock(message=message, finish_reason="stop")
    usage = MagicMock(prompt_tokens=10, completion_tokens=5)
    return MagicMock(choices=[choice], usage=usage, model=model, id="resp-id")


def _build_provider(*, max_retries: int = 3) -> OpenAIProvider:
    return OpenAIProvider(api_key="test-key", max_retries=max_retries, base_backoff_seconds=0.0)


def _mock_create(provider: OpenAIProvider) -> AsyncMock:
    mock = AsyncMock()
    provider._client.chat.completions.create = mock  # pyright: ignore[reportPrivateUsage]
    return mock


def _rate_limit_error() -> RateLimitError:
    return RateLimitError.__new__(RateLimitError)


def _timeout_error() -> APITimeoutError:
    return APITimeoutError.__new__(APITimeoutError)


def _server_error() -> InternalServerError:
    return InternalServerError.__new__(InternalServerError)


async def test_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("COMPACTBENCH_OPENAI_API_KEY", raising=False)
    with pytest.raises(ProviderError, match="OpenAI API key"):
        OpenAIProvider()


async def test_uses_env_var_when_api_key_not_passed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COMPACTBENCH_OPENAI_API_KEY", "env-key")
    provider = OpenAIProvider()
    assert provider is not None


async def test_complete_returns_parsed_response() -> None:
    provider = _build_provider()
    mock = _mock_create(provider)
    mock.return_value = _ok_response("hello", model="gpt-4o")

    resp = await provider.complete(CompletionRequest(model="gpt-4o", prompt="say hi"))

    assert resp.text == "hello"
    assert resp.prompt_tokens == 10
    assert resp.completion_tokens == 5
    assert resp.model == "gpt-4o"
    assert resp.raw["provider"] == "openai"
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


async def test_retries_on_internal_server_error() -> None:
    provider = _build_provider(max_retries=2)
    mock = _mock_create(provider)
    mock.side_effect = [_server_error(), _ok_response()]

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


async def test_cached_prefix_is_prepended_to_user_content() -> None:
    """OpenAI auto-caching picks up stable prefixes at the start of user content."""
    provider = _build_provider()
    mock = _mock_create(provider)
    mock.return_value = _ok_response()

    await provider.complete(
        CompletionRequest(
            model="m",
            prompt="item question",
            cached_prefix="STATIC ARTIFACT CONTEXT ",
        )
    )
    assert mock.await_args is not None
    messages = mock.await_args.kwargs["messages"]
    assert messages[-1] == {
        "role": "user",
        "content": "STATIC ARTIFACT CONTEXT item question",
    }


async def test_no_cached_prefix_leaves_prompt_untouched() -> None:
    provider = _build_provider()
    mock = _mock_create(provider)
    mock.return_value = _ok_response()

    await provider.complete(CompletionRequest(model="m", prompt="hi"))
    assert mock.await_args is not None
    assert mock.await_args.kwargs["messages"][-1]["content"] == "hi"
