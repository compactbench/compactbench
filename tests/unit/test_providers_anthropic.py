"""Anthropic provider tests (SDK mocked)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from anthropic import APITimeoutError, InternalServerError, RateLimitError

from compactbench.providers import (
    AnthropicProvider,
    CompletionRequest,
    ProviderError,
    ProviderResponseError,
)

pytestmark = pytest.mark.unit


def _ok_response(text: str = "the answer", model: str = "claude-3-5-haiku-latest") -> MagicMock:
    block = MagicMock(type="text", text=text)
    usage = MagicMock(input_tokens=10, output_tokens=5)
    return MagicMock(
        content=[block],
        usage=usage,
        model=model,
        id="msg-id",
        stop_reason="end_turn",
    )


def _build_provider(*, max_retries: int = 3) -> AnthropicProvider:
    return AnthropicProvider(api_key="test-key", max_retries=max_retries, base_backoff_seconds=0.0)


def _mock_create(provider: AnthropicProvider) -> AsyncMock:
    mock = AsyncMock()
    provider._client.messages.create = mock  # pyright: ignore[reportPrivateUsage]
    return mock


def _rate_limit_error() -> RateLimitError:
    return RateLimitError.__new__(RateLimitError)


def _timeout_error() -> APITimeoutError:
    return APITimeoutError.__new__(APITimeoutError)


def _server_error() -> InternalServerError:
    return InternalServerError.__new__(InternalServerError)


async def test_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("COMPACTBENCH_ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(ProviderError, match="Anthropic API key"):
        AnthropicProvider()


async def test_uses_env_var_when_api_key_not_passed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COMPACTBENCH_ANTHROPIC_API_KEY", "env-key")
    provider = AnthropicProvider()
    assert provider is not None


async def test_complete_returns_parsed_response() -> None:
    provider = _build_provider()
    mock = _mock_create(provider)
    mock.return_value = _ok_response("hello", model="claude-3-5-haiku")

    resp = await provider.complete(CompletionRequest(model="claude-3-5-haiku", prompt="say hi"))

    assert resp.text == "hello"
    assert resp.prompt_tokens == 10
    assert resp.completion_tokens == 5
    assert resp.model == "claude-3-5-haiku"
    assert resp.raw["provider"] == "anthropic"
    assert resp.raw["stop_reason"] == "end_turn"


async def test_complete_passes_system_as_top_level_kwarg() -> None:
    """Anthropic takes `system` as a top-level arg, not as a message role."""
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
        )
    )

    assert mock.await_args is not None
    kwargs = mock.await_args.kwargs
    assert kwargs["model"] == "m"
    assert kwargs["max_tokens"] == 123
    assert kwargs["temperature"] == 0.2
    assert kwargs["system"] == "sys"
    assert kwargs["messages"] == [{"role": "user", "content": "p"}]


async def test_omits_system_when_not_provided() -> None:
    provider = _build_provider()
    mock = _mock_create(provider)
    mock.return_value = _ok_response()

    await provider.complete(CompletionRequest(model="m", prompt="p"))
    assert mock.await_args is not None
    assert "system" not in mock.await_args.kwargs


async def test_concatenates_multiple_text_blocks() -> None:
    provider = _build_provider()
    mock = _mock_create(provider)
    blocks = [
        MagicMock(type="text", text="hello "),
        MagicMock(type="tool_use", text="ignored"),
        MagicMock(type="text", text="world"),
    ]
    mock.return_value = MagicMock(
        content=blocks,
        usage=MagicMock(input_tokens=1, output_tokens=1),
        model="m",
        id="id",
        stop_reason="end_turn",
    )

    resp = await provider.complete(CompletionRequest(model="m", prompt="p"))
    assert resp.text == "hello world"


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


async def test_raises_on_no_text_blocks() -> None:
    provider = _build_provider()
    mock = _mock_create(provider)
    mock.return_value = MagicMock(
        content=[],
        usage=MagicMock(input_tokens=1, output_tokens=1),
        model="m",
        id="id",
        stop_reason="end_turn",
    )

    with pytest.raises(ProviderResponseError, match="no text content"):
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


async def test_cached_prefix_wraps_content_in_cache_control_blocks() -> None:
    """Caller-supplied cached_prefix becomes a content block marked ephemeral."""
    provider = _build_provider()
    mock = _mock_create(provider)
    mock.return_value = _ok_response()

    await provider.complete(
        CompletionRequest(
            model="m",
            prompt="item question",
            cached_prefix="STATIC ARTIFACT CONTEXT",
        )
    )

    assert mock.await_args is not None
    messages = mock.await_args.kwargs["messages"]
    assert len(messages) == 1
    content = messages[0]["content"]
    # Expect a list of two text blocks; the first marked for ephemeral caching.
    assert isinstance(content, list)
    blocks: list[dict[str, object]] = list(content)
    assert len(blocks) == 2
    assert blocks[0] == {
        "type": "text",
        "text": "STATIC ARTIFACT CONTEXT",
        "cache_control": {"type": "ephemeral"},
    }
    assert blocks[1] == {"type": "text", "text": "item question"}


async def test_no_cached_prefix_uses_simple_string_content() -> None:
    """Legacy single-prompt requests stay as a plain string on the user message."""
    provider = _build_provider()
    mock = _mock_create(provider)
    mock.return_value = _ok_response()

    await provider.complete(CompletionRequest(model="m", prompt="hi"))
    assert mock.await_args is not None
    content = mock.await_args.kwargs["messages"][0]["content"]
    assert content == "hi"
