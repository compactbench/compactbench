"""Google AI Studio provider tests (SDK mocked)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from google.genai import errors as genai_errors

from compactbench.providers import (
    CompletionRequest,
    GoogleAIStudioProvider,
    ProviderError,
)

pytestmark = pytest.mark.unit


def _ok_response(text: str = "the answer", finish_reason: str = "STOP") -> MagicMock:
    usage = MagicMock(prompt_token_count=12, candidates_token_count=7)
    candidate = MagicMock(finish_reason=finish_reason)
    return MagicMock(text=text, usage_metadata=usage, candidates=[candidate])


def _build_provider(*, max_retries: int = 3) -> GoogleAIStudioProvider:
    return GoogleAIStudioProvider(
        api_key="test-key",
        max_retries=max_retries,
        base_backoff_seconds=0.0,
    )


def _mock_generate(provider: GoogleAIStudioProvider) -> AsyncMock:
    mock = AsyncMock()
    provider._client.aio.models.generate_content = mock  # pyright: ignore[reportPrivateUsage]
    return mock


def _api_error(code: int) -> genai_errors.APIError:
    err = genai_errors.APIError.__new__(genai_errors.APIError)
    err.code = code  # pyright: ignore[reportAttributeAccessIssue]
    return err


async def test_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("COMPACTBENCH_GOOGLE_AI_STUDIO_API_KEY", raising=False)
    with pytest.raises(ProviderError, match="Google AI Studio API key"):
        GoogleAIStudioProvider()


async def test_uses_env_var_when_api_key_not_passed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("COMPACTBENCH_GOOGLE_AI_STUDIO_API_KEY", "env-key")
    provider = GoogleAIStudioProvider()
    assert provider is not None


async def test_complete_returns_parsed_response() -> None:
    provider = _build_provider()
    mock = _mock_generate(provider)
    mock.return_value = _ok_response("hello")

    resp = await provider.complete(CompletionRequest(model="gemini-3.8-flash", prompt="p"))

    assert resp.text == "hello"
    assert resp.prompt_tokens == 12
    assert resp.completion_tokens == 7
    assert resp.model == "gemini-3.8-flash"
    assert resp.raw["provider"] == "google-ai-studio"


async def test_forwards_system_instruction_and_json_mime() -> None:
    provider = _build_provider()
    mock = _mock_generate(provider)
    mock.return_value = _ok_response()

    await provider.complete(
        CompletionRequest(
            model="m",
            prompt="p",
            system="be helpful",
            response_format={"type": "json_object"},
            max_tokens=500,
            temperature=0.0,
        )
    )

    assert mock.await_args is not None
    config = mock.await_args.kwargs["config"]
    assert config.system_instruction == "be helpful"
    assert config.response_mime_type == "application/json"
    assert config.response_json_schema is None
    assert config.max_output_tokens == 500
    assert config.temperature == 0.0


async def test_temperature_is_omitted_when_not_requested() -> None:
    provider = _build_provider()
    mock = _mock_generate(provider)
    mock.return_value = _ok_response()

    await provider.complete(CompletionRequest(model="m", prompt="p", reasoning_effort="low"))
    assert mock.await_args is not None
    config = mock.await_args.kwargs["config"]
    assert config.temperature is None
    assert config.response_mime_type is None
    assert config.thinking_config is None


async def test_json_schema_maps_to_response_json_schema() -> None:
    provider = _build_provider()
    mock = _mock_generate(provider)
    mock.return_value = _ok_response('{"a": 1}')
    schema = {
        "type": "object",
        "properties": {"a": {"type": "integer"}},
        "required": ["a"],
        "additionalProperties": False,
    }

    await provider.complete(CompletionRequest(model="m", prompt="p", json_schema=schema))
    assert mock.await_args is not None
    config = mock.await_args.kwargs["config"]
    assert config.response_mime_type == "application/json"
    assert config.response_json_schema == schema
    assert config.response_schema is None


async def test_retries_on_429() -> None:
    provider = _build_provider(max_retries=3)
    mock = _mock_generate(provider)
    mock.side_effect = [_api_error(429), _ok_response()]

    await provider.complete(CompletionRequest(model="m", prompt="p"))
    assert mock.await_count == 2


async def test_retries_on_5xx() -> None:
    provider = _build_provider(max_retries=3)
    mock = _mock_generate(provider)
    mock.side_effect = [_api_error(503), _ok_response()]

    await provider.complete(CompletionRequest(model="m", prompt="p"))
    assert mock.await_count == 2


async def test_does_not_retry_on_4xx_other_than_429() -> None:
    provider = _build_provider(max_retries=3)
    mock = _mock_generate(provider)
    mock.side_effect = [_api_error(400)]

    with pytest.raises(genai_errors.APIError):
        await provider.complete(CompletionRequest(model="m", prompt="p"))
    assert mock.await_count == 1


async def test_handles_missing_usage_metadata() -> None:
    provider = _build_provider()
    mock = _mock_generate(provider)
    response = _ok_response()
    response.usage_metadata = None
    mock.return_value = response

    resp = await provider.complete(CompletionRequest(model="m", prompt="p"))
    assert resp.prompt_tokens == 0
    assert resp.completion_tokens == 0
