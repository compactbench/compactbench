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
from compactbench.providers._retry import RATE_LIMIT_RETRIES

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
    assert kwargs["max_completion_tokens"] == 123
    assert "max_tokens" not in kwargs
    assert kwargs["temperature"] == 0.2
    assert kwargs["response_format"] == {"type": "json_object"}
    assert kwargs["messages"] == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "p"},
    ]


async def test_omits_optional_parameters_when_not_requested() -> None:
    """Reasoning models reject a non-default temperature, so None must not be sent."""
    provider = _build_provider()
    mock = _mock_create(provider)
    mock.return_value = _ok_response()

    await provider.complete(CompletionRequest(model="m", prompt="p"))
    assert mock.await_args is not None
    kwargs = mock.await_args.kwargs
    assert "response_format" not in kwargs
    assert "temperature" not in kwargs
    assert "reasoning_effort" not in kwargs


async def test_custom_base_url_keeps_max_tokens() -> None:
    """OpenAI-compatible servers accept the original `max_tokens` name."""
    provider = OpenAIProvider(api_key="k", base_url="http://localhost:8000/v1")
    mock = _mock_create(provider)
    mock.return_value = _ok_response()

    await provider.complete(CompletionRequest(model="m", prompt="p", max_tokens=77))
    assert mock.await_args is not None
    assert mock.await_args.kwargs["max_tokens"] == 77
    assert "max_completion_tokens" not in mock.await_args.kwargs


async def test_json_schema_maps_to_strict_json_schema_response_format() -> None:
    provider = _build_provider()
    mock = _mock_create(provider)
    mock.return_value = _ok_response('{"a": 1}')
    schema = {
        "type": "object",
        "properties": {"a": {"type": "integer"}},
        "required": ["a"],
        "additionalProperties": False,
    }

    await provider.complete(
        CompletionRequest(
            model="m",
            prompt="p",
            json_schema=schema,
            response_format={"type": "json_object"},
        )
    )
    assert mock.await_args is not None
    assert mock.await_args.kwargs["response_format"] == {
        "type": "json_schema",
        "json_schema": {"name": "response", "schema": schema, "strict": True},
    }


async def test_reasoning_effort_is_forwarded() -> None:
    provider = _build_provider()
    mock = _mock_create(provider)
    mock.return_value = _ok_response()

    await provider.complete(CompletionRequest(model="m", prompt="p", reasoning_effort="medium"))
    assert mock.await_args is not None
    assert mock.await_args.kwargs["reasoning_effort"] == "medium"


async def test_refusal_raises() -> None:
    provider = _build_provider()
    mock = _mock_create(provider)
    response = _ok_response()
    response.choices[0].message = MagicMock(content=None, refusal="I can't help with that.")
    mock.return_value = response

    with pytest.raises(ProviderResponseError, match="declined"):
        await provider.complete(CompletionRequest(model="m", prompt="p"))


async def test_length_stop_with_no_text_raises_clear_error() -> None:
    """Reasoning tokens count toward max_completion_tokens and can use all of it."""
    provider = _build_provider()
    mock = _mock_create(provider)
    response = _ok_response("")
    response.choices[0].finish_reason = "length"
    mock.return_value = response

    with pytest.raises(ProviderResponseError, match="before writing any text"):
        await provider.complete(CompletionRequest(model="m", prompt="p", max_tokens=64))


async def test_length_stop_with_partial_text_returns_the_text() -> None:
    provider = _build_provider()
    mock = _mock_create(provider)
    response = _ok_response("truncated answ")
    response.choices[0].finish_reason = "length"
    mock.return_value = response

    resp = await provider.complete(CompletionRequest(model="m", prompt="p"))
    assert resp.text == "truncated answ"
    assert resp.raw["finish_reason"] == "length"


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


async def test_base_url_is_passed_to_the_sdk() -> None:
    provider = OpenAIProvider(api_key="k", base_url="http://localhost:8000/v1")
    assert str(provider._client.base_url).rstrip("/") == "http://localhost:8000/v1"  # pyright: ignore[reportPrivateUsage]


async def test_base_url_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COMPACTBENCH_OPENAI_BASE_URL", "http://localhost:1234/v1")
    provider = OpenAIProvider(api_key="k")
    assert str(provider._client.base_url).rstrip("/") == "http://localhost:1234/v1"  # pyright: ignore[reportPrivateUsage]


async def test_base_url_makes_the_api_key_optional(monkeypatch: pytest.MonkeyPatch) -> None:
    """Self-hosted servers do not check a key, and requiring one would block them."""
    monkeypatch.delenv("COMPACTBENCH_OPENAI_API_KEY", raising=False)
    provider = OpenAIProvider(base_url="http://localhost:8000/v1")
    assert provider is not None


async def test_still_requires_a_key_without_a_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """The relaxation must not leak into the hosted path, where a key is mandatory."""
    monkeypatch.delenv("COMPACTBENCH_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("COMPACTBENCH_OPENAI_BASE_URL", raising=False)
    with pytest.raises(ProviderError, match="OpenAI API key"):
        OpenAIProvider()


async def test_custom_base_url_is_flagged_in_raw() -> None:
    provider = OpenAIProvider(api_key="k", base_url="http://localhost:8000/v1")
    mock = _mock_create(provider)
    mock.return_value = _ok_response()

    resp = await provider.complete(CompletionRequest(model="m", prompt="p"))
    assert resp.raw["custom_base_url"] is True


async def test_default_client_is_not_flagged_as_custom(monkeypatch: pytest.MonkeyPatch) -> None:
    # Explicitly unset: a developer with the env var exported would otherwise see this
    # fail for a reason that has nothing to do with the code under test.
    monkeypatch.delenv("COMPACTBENCH_OPENAI_BASE_URL", raising=False)
    provider = _build_provider()
    mock = _mock_create(provider)
    mock.return_value = _ok_response()

    resp = await provider.complete(CompletionRequest(model="m", prompt="p"))
    assert resp.raw["custom_base_url"] is False


async def test_empty_base_url_env_is_not_treated_as_custom(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An exported-but-empty base URL must not mark a real OpenAI run as custom.

    Regression for the two-gate mismatch: the client was gated on truthiness
    (so "" correctly fell back to api.openai.com) while provenance was gated on
    identity (`"" is not None` → True), stamping a genuine hosted run as
    self-hosted. That is the one direction the flag must never get wrong.
    """
    monkeypatch.setenv("COMPACTBENCH_OPENAI_BASE_URL", "")
    provider = OpenAIProvider(api_key="k")
    assert provider.endpoint_kind == "default"
    mock = _mock_create(provider)
    mock.return_value = _ok_response()
    resp = await provider.complete(CompletionRequest(model="m", prompt="p"))
    assert resp.raw["custom_base_url"] is False


async def test_whitespace_only_base_url_is_not_treated_as_custom(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("COMPACTBENCH_OPENAI_BASE_URL", "   ")
    provider = OpenAIProvider(api_key="k")
    assert provider.endpoint_kind == "default"


@pytest.mark.parametrize("bad", ["localhost:8000/v1", "not a url", "ftp://host/v1"])
async def test_base_url_without_http_scheme_is_rejected(bad: str) -> None:
    """A scheme-less base URL is the likeliest typo here; fail at construction.

    The SDK accepts any string, so these previously surfaced as an opaque
    connection error part-way into a run rather than immediately.
    """
    with pytest.raises(ProviderError, match="must start with http"):
        OpenAIProvider(api_key="k", base_url=bad)


async def test_endpoint_kind_is_custom_for_a_base_url() -> None:
    provider = OpenAIProvider(api_key="k", base_url="http://localhost:8000/v1")
    assert provider.endpoint_kind == "custom"


async def test_endpoint_kind_is_default_without_a_base_url() -> None:
    assert OpenAIProvider(api_key="k").endpoint_kind == "default"
