"""Ollama provider tests (SDK mocked)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from ollama import ResponseError

from compactbench.providers import CompletionRequest, OllamaProvider

pytestmark = pytest.mark.unit


def _ok_response(text: str = "the answer") -> MagicMock:
    message = MagicMock(content=text)
    return MagicMock(
        message=message,
        prompt_eval_count=8,
        eval_count=4,
        done_reason="stop",
    )


def _build_provider(*, max_retries: int = 3) -> OllamaProvider:
    return OllamaProvider(
        base_url="http://localhost:11434",
        max_retries=max_retries,
        base_backoff_seconds=0.0,
    )


def _mock_chat(provider: OllamaProvider) -> AsyncMock:
    mock = AsyncMock()
    provider._client.chat = mock  # pyright: ignore[reportPrivateUsage]
    return mock


def _response_error(status_code: int) -> ResponseError:
    err = ResponseError.__new__(ResponseError)
    err.status_code = status_code  # pyright: ignore[reportAttributeAccessIssue]
    return err


async def test_uses_default_base_url_when_env_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("COMPACTBENCH_OLLAMA_BASE_URL", raising=False)
    provider = OllamaProvider()
    assert provider is not None


async def test_uses_env_var_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COMPACTBENCH_OLLAMA_BASE_URL", "http://remote:11434")
    provider = OllamaProvider()
    assert provider is not None


async def test_complete_returns_parsed_response() -> None:
    provider = _build_provider()
    mock = _mock_chat(provider)
    mock.return_value = _ok_response("hello")

    resp = await provider.complete(CompletionRequest(model="llama3.2", prompt="p"))

    assert resp.text == "hello"
    assert resp.prompt_tokens == 8
    assert resp.completion_tokens == 4
    assert resp.model == "llama3.2"
    assert resp.raw["provider"] == "ollama"
    assert resp.raw["done_reason"] == "stop"


async def test_forwards_messages_and_options() -> None:
    provider = _build_provider()
    mock = _mock_chat(provider)
    mock.return_value = _ok_response()

    await provider.complete(
        CompletionRequest(
            model="llama3.2",
            prompt="p",
            system="be brief",
            max_tokens=100,
            temperature=0.3,
        )
    )

    assert mock.await_args is not None
    kwargs = mock.await_args.kwargs
    assert kwargs["model"] == "llama3.2"
    assert kwargs["messages"] == [
        {"role": "system", "content": "be brief"},
        {"role": "user", "content": "p"},
    ]
    assert kwargs["options"] == {"temperature": 0.3, "num_predict": 100}
    assert "format" not in kwargs


async def test_json_response_format_sets_format_json() -> None:
    provider = _build_provider()
    mock = _mock_chat(provider)
    mock.return_value = _ok_response()

    await provider.complete(
        CompletionRequest(
            model="m",
            prompt="p",
            response_format={"type": "json_object"},
        )
    )
    assert mock.await_args is not None
    assert mock.await_args.kwargs["format"] == "json"


async def test_retries_on_timeout() -> None:
    provider = _build_provider(max_retries=3)
    mock = _mock_chat(provider)
    mock.side_effect = [httpx.ReadTimeout("slow"), _ok_response()]

    await provider.complete(CompletionRequest(model="m", prompt="p"))
    assert mock.await_count == 2


async def test_retries_on_connect_error() -> None:
    provider = _build_provider(max_retries=3)
    mock = _mock_chat(provider)
    mock.side_effect = [httpx.ConnectError("unreachable"), _ok_response()]

    await provider.complete(CompletionRequest(model="m", prompt="p"))
    assert mock.await_count == 2


async def test_retries_on_5xx_response_error() -> None:
    provider = _build_provider(max_retries=3)
    mock = _mock_chat(provider)
    mock.side_effect = [_response_error(503), _ok_response()]

    await provider.complete(CompletionRequest(model="m", prompt="p"))
    assert mock.await_count == 2


async def test_does_not_retry_on_4xx_other_than_429() -> None:
    provider = _build_provider(max_retries=3)
    mock = _mock_chat(provider)
    mock.side_effect = [_response_error(404)]

    with pytest.raises(ResponseError):
        await provider.complete(CompletionRequest(model="m", prompt="p"))
    assert mock.await_count == 1
