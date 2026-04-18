"""Cross-provider contract tests.

Every provider returns a :class:`CompletionResponse` with consistent types on
every field and a ``raw["provider"]`` key that names the provider.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from compactbench.providers import (
    AnthropicProvider,
    CompletionRequest,
    CompletionResponse,
    GoogleAIStudioProvider,
    GroqProvider,
    MockProvider,
    OllamaProvider,
    OpenAIProvider,
    Provider,
    list_providers,
)

pytestmark = pytest.mark.unit


def _make_mock_provider() -> MockProvider:
    return MockProvider(default="hello")


def _make_groq_provider() -> GroqProvider:
    provider = GroqProvider(api_key="fake", base_backoff_seconds=0.0)
    message = MagicMock(content="hello")
    choice = MagicMock(message=message, finish_reason="stop")
    usage = MagicMock(prompt_tokens=3, completion_tokens=2)
    response = MagicMock(choices=[choice], usage=usage, model="m", id="id")
    provider._client.chat.completions.create = AsyncMock(return_value=response)  # pyright: ignore[reportPrivateUsage]
    return provider


def _make_google_provider() -> GoogleAIStudioProvider:
    provider = GoogleAIStudioProvider(api_key="fake", base_backoff_seconds=0.0)
    usage = MagicMock(prompt_token_count=3, candidates_token_count=2)
    candidate = MagicMock(finish_reason="STOP")
    response = MagicMock(text="hello", usage_metadata=usage, candidates=[candidate])
    provider._client.aio.models.generate_content = AsyncMock(return_value=response)  # pyright: ignore[reportPrivateUsage]
    return provider


def _make_ollama_provider() -> OllamaProvider:
    provider = OllamaProvider(base_backoff_seconds=0.0)
    message = MagicMock(content="hello")
    response = MagicMock(message=message, prompt_eval_count=3, eval_count=2, done_reason="stop")
    provider._client.chat = AsyncMock(return_value=response)  # pyright: ignore[reportPrivateUsage]
    return provider


def _make_anthropic_provider() -> AnthropicProvider:
    provider = AnthropicProvider(api_key="fake", base_backoff_seconds=0.0)
    block = MagicMock(type="text", text="hello")
    usage = MagicMock(input_tokens=3, output_tokens=2)
    response = MagicMock(content=[block], usage=usage, model="m", id="id", stop_reason="end_turn")
    provider._client.messages.create = AsyncMock(return_value=response)  # pyright: ignore[reportPrivateUsage]
    return provider


def _make_openai_provider() -> OpenAIProvider:
    provider = OpenAIProvider(api_key="fake", base_backoff_seconds=0.0)
    message = MagicMock(content="hello")
    choice = MagicMock(message=message, finish_reason="stop")
    usage = MagicMock(prompt_tokens=3, completion_tokens=2)
    response = MagicMock(choices=[choice], usage=usage, model="m", id="id")
    provider._client.chat.completions.create = AsyncMock(return_value=response)  # pyright: ignore[reportPrivateUsage]
    return provider


def _assert_contract(response: CompletionResponse, expected_key: str) -> None:
    assert isinstance(response, CompletionResponse)
    assert response.text == "hello"
    assert isinstance(response.prompt_tokens, int)
    assert isinstance(response.completion_tokens, int)
    assert isinstance(response.model, str)
    assert isinstance(response.raw, dict)
    assert response.raw.get("provider") == expected_key
    assert response.prompt_tokens >= 0
    assert response.completion_tokens >= 0


def test_all_providers_are_registered() -> None:
    assert set(list_providers()) == {
        "mock",
        "groq",
        "google-ai-studio",
        "ollama",
        "anthropic",
        "openai",
    }


async def test_mock_provider_meets_contract() -> None:
    provider: Provider = _make_mock_provider()
    response = await provider.complete(CompletionRequest(model="any", prompt="hi"))
    _assert_contract(response, "mock")


async def test_groq_provider_meets_contract() -> None:
    provider: Provider = _make_groq_provider()
    response = await provider.complete(CompletionRequest(model="any", prompt="hi"))
    _assert_contract(response, "groq")


async def test_google_ai_studio_provider_meets_contract() -> None:
    provider: Provider = _make_google_provider()
    response = await provider.complete(CompletionRequest(model="any", prompt="hi"))
    _assert_contract(response, "google-ai-studio")


async def test_ollama_provider_meets_contract() -> None:
    provider: Provider = _make_ollama_provider()
    response = await provider.complete(CompletionRequest(model="any", prompt="hi"))
    _assert_contract(response, "ollama")


async def test_anthropic_provider_meets_contract() -> None:
    provider: Provider = _make_anthropic_provider()
    response = await provider.complete(CompletionRequest(model="any", prompt="hi"))
    _assert_contract(response, "anthropic")


async def test_openai_provider_meets_contract() -> None:
    provider: Provider = _make_openai_provider()
    response = await provider.complete(CompletionRequest(model="any", prompt="hi"))
    _assert_contract(response, "openai")
