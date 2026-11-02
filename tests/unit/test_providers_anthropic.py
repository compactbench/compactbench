"""Anthropic provider tests (SDK mocked)."""

from __future__ import annotations

from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from anthropic import APITimeoutError, InternalServerError, OverloadedError, RateLimitError

from compactbench.providers import (
    AnthropicProvider,
    CompletionRequest,
    ProviderError,
    ProviderResponseError,
)
from compactbench.providers._retry import RATE_LIMIT_RETRIES
from compactbench.providers.anthropic import MIN_MAX_TOKENS

pytestmark = pytest.mark.unit


def _ok_response(text: str = "the answer", model: str = "claude-haiku-5-5") -> MagicMock:
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


def _overloaded_error() -> OverloadedError:
    return OverloadedError.__new__(OverloadedError)


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
    mock.return_value = _ok_response("hello", model="claude-haiku-5-5")

    resp = await provider.complete(CompletionRequest(model="claude-haiku-5-5", prompt="say hi"))

    assert resp.text == "hello"
    assert resp.prompt_tokens == 10
    assert resp.completion_tokens == 5
    assert resp.model == "claude-haiku-5-5"
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
            max_tokens=4000,
        )
    )

    assert mock.await_args is not None
    kwargs = mock.await_args.kwargs
    assert kwargs["model"] == "m"
    assert kwargs["max_tokens"] == 4000
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


async def test_gives_up_after_rate_limit_retries_run_out() -> None:
    # Rate limits get their own, larger attempt budget than other errors.
    provider = _build_provider(max_retries=2)
    mock = _mock_create(provider)
    mock.side_effect = [_rate_limit_error()] * RATE_LIMIT_RETRIES

    with pytest.raises(RateLimitError):
        await provider.complete(CompletionRequest(model="m", prompt="p"))
    assert mock.await_count == RATE_LIMIT_RETRIES


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
    blocks = cast(list[Any], content)
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


async def test_never_sends_sampling_parameters() -> None:
    """API version 2026-10-21 rejects temperature/top_p/top_k on every model."""
    provider = _build_provider()
    mock = _mock_create(provider)
    mock.return_value = _ok_response()

    await provider.complete(CompletionRequest(model="m", prompt="p", temperature=0.2))
    await provider.complete(CompletionRequest(model="m", prompt="p"))

    assert mock.await_count == 2
    for call in mock.await_args_list:
        assert not {"temperature", "top_p", "top_k"} & set(call.kwargs)


async def test_small_max_tokens_is_raised_to_the_floor() -> None:
    """Adaptive thinking counts toward max_tokens, so a tiny cap leaves no room for text."""
    provider = _build_provider()
    mock = _mock_create(provider)
    mock.return_value = _ok_response()

    await provider.complete(CompletionRequest(model="m", prompt="p", max_tokens=50))
    assert mock.await_args is not None
    assert mock.await_args.kwargs["max_tokens"] == MIN_MAX_TOKENS


async def test_omits_output_config_by_default() -> None:
    """The Messages API has no schema-less JSON mode, so json_object is not forwarded."""
    provider = _build_provider()
    mock = _mock_create(provider)
    mock.return_value = _ok_response()

    await provider.complete(
        CompletionRequest(model="m", prompt="p", response_format={"type": "json_object"})
    )
    assert mock.await_args is not None
    assert "output_config" not in mock.await_args.kwargs
    assert "response_format" not in mock.await_args.kwargs


async def test_json_schema_maps_to_output_config_format() -> None:
    provider = _build_provider()
    mock = _mock_create(provider)
    mock.return_value = _ok_response('{"a": 1}')
    schema = {
        "type": "object",
        "properties": {"a": {"type": "integer"}},
        "required": ["a"],
        "additionalProperties": False,
    }

    await provider.complete(CompletionRequest(model="m", prompt="p", json_schema=schema))
    assert mock.await_args is not None
    assert mock.await_args.kwargs["output_config"] == {
        "format": {"type": "json_schema", "schema": schema}
    }


async def test_reasoning_effort_maps_to_output_config_effort() -> None:
    provider = _build_provider()
    mock = _mock_create(provider)
    mock.return_value = _ok_response()

    await provider.complete(CompletionRequest(model="m", prompt="p", reasoning_effort="low"))
    assert mock.await_args is not None
    assert mock.await_args.kwargs["output_config"] == {"effort": "low"}


async def test_json_schema_and_effort_share_output_config() -> None:
    provider = _build_provider()
    mock = _mock_create(provider)
    mock.return_value = _ok_response("{}")
    schema: dict[str, Any] = {"type": "object", "properties": {}, "additionalProperties": False}

    await provider.complete(
        CompletionRequest(model="m", prompt="p", json_schema=schema, reasoning_effort="high")
    )
    assert mock.await_args is not None
    assert mock.await_args.kwargs["output_config"] == {
        "format": {"type": "json_schema", "schema": schema},
        "effort": "high",
    }


async def test_thinking_blocks_are_not_part_of_the_text() -> None:
    provider = _build_provider()
    mock = _mock_create(provider)
    mock.return_value = MagicMock(
        content=[
            MagicMock(type="thinking", thinking="", text="not an answer"),
            MagicMock(type="text", text="the answer"),
        ],
        usage=MagicMock(input_tokens=1, output_tokens=1),
        model="m",
        id="id",
        stop_reason="end_turn",
    )

    resp = await provider.complete(CompletionRequest(model="m", prompt="p"))
    assert resp.text == "the answer"


async def test_refusal_raises_with_category() -> None:
    """A decline is an HTTP 200; any partial text must not be returned as an answer."""
    provider = _build_provider()
    mock = _mock_create(provider)
    mock.return_value = MagicMock(
        content=[MagicMock(type="text", text="partial")],
        usage=MagicMock(input_tokens=1, output_tokens=1),
        model="m",
        id="id",
        stop_reason="refusal",
        stop_details=MagicMock(type="refusal", category="cyber"),
    )

    with pytest.raises(ProviderResponseError, match=r"refusal.*'cyber'"):
        await provider.complete(CompletionRequest(model="m", prompt="p"))


async def test_refusal_without_stop_details_still_raises() -> None:
    provider = _build_provider()
    mock = _mock_create(provider)
    mock.return_value = MagicMock(
        content=[],
        usage=MagicMock(input_tokens=1, output_tokens=0),
        model="m",
        id="id",
        stop_reason="refusal",
        stop_details=None,
    )

    with pytest.raises(ProviderResponseError, match="category=None"):
        await provider.complete(CompletionRequest(model="m", prompt="p"))


async def test_max_tokens_with_only_thinking_raises_clear_error() -> None:
    """Thinking that spends the whole budget must not surface as an empty answer."""
    provider = _build_provider()
    mock = _mock_create(provider)
    mock.return_value = MagicMock(
        content=[MagicMock(type="thinking", thinking="")],
        usage=MagicMock(input_tokens=1, output_tokens=MIN_MAX_TOKENS),
        model="m",
        id="id",
        stop_reason="max_tokens",
    )

    with pytest.raises(ProviderResponseError, match="max_tokens=1024 before writing any text"):
        await provider.complete(CompletionRequest(model="m", prompt="p", max_tokens=10))


async def test_max_tokens_with_partial_text_returns_the_text() -> None:
    provider = _build_provider()
    mock = _mock_create(provider)
    response = _ok_response("truncated answ")
    response.stop_reason = "max_tokens"
    mock.return_value = response

    resp = await provider.complete(CompletionRequest(model="m", prompt="p"))
    assert resp.text == "truncated answ"
    assert resp.raw["stop_reason"] == "max_tokens"


async def test_retries_on_overloaded_error() -> None:
    """529 maps to OverloadedError, which does not subclass InternalServerError."""
    provider = _build_provider(max_retries=2)
    mock = _mock_create(provider)
    mock.side_effect = [_overloaded_error(), _ok_response()]

    resp = await provider.complete(CompletionRequest(model="m", prompt="p"))
    assert resp is not None
    assert mock.await_count == 2


async def test_cache_token_telemetry_is_surfaced_in_raw() -> None:
    provider = _build_provider()
    mock = _mock_create(provider)
    response = _ok_response()
    response.usage = MagicMock(
        input_tokens=10,
        output_tokens=5,
        cache_read_input_tokens=900,
        cache_creation_input_tokens=0,
    )
    mock.return_value = response

    resp = await provider.complete(
        CompletionRequest(model="m", prompt="q", cached_prefix="STATIC CONTEXT")
    )
    assert resp.raw["cache_read_input_tokens"] == 900
    assert resp.raw["cache_creation_input_tokens"] == 0
