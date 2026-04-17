"""Groq Cloud provider (Llama 3.3 70B, Kimi K2, etc.).

Requires ``compactbench[providers]`` (installs the ``groq`` SDK) and a
``COMPACTBENCH_GROQ_API_KEY`` environment variable.
"""

from __future__ import annotations

import os
from typing import Any, ClassVar

from compactbench.providers._retry import retry_with_backoff
from compactbench.providers.base import (
    CompletionRequest,
    CompletionResponse,
    Provider,
)
from compactbench.providers.errors import ProviderError, ProviderResponseError


class GroqProvider(Provider):
    """Async Groq client with rate-limit backoff."""

    key: ClassVar[str] = "groq"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        max_retries: int = 3,
        base_backoff_seconds: float = 2.0,
    ) -> None:
        try:
            from groq import AsyncGroq
        except ImportError as exc:
            raise ProviderError(
                "groq SDK is not installed. Install with: pip install 'compactbench[providers]'"
            ) from exc

        resolved_key = api_key or os.environ.get("COMPACTBENCH_GROQ_API_KEY")
        if not resolved_key:
            raise ProviderError(
                "Groq API key required. Set COMPACTBENCH_GROQ_API_KEY or pass api_key=."
            )

        self._client: Any = AsyncGroq(api_key=resolved_key)
        self._max_retries = max_retries
        self._base_backoff_seconds = base_backoff_seconds

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        from groq import APIConnectionError, APITimeoutError, RateLimitError

        def _is_retryable(exc: Exception) -> bool:
            return isinstance(exc, RateLimitError | APITimeoutError | APIConnectionError)

        messages: list[dict[str, str]] = []
        if request.system:
            messages.append({"role": "system", "content": request.system})
        messages.append({"role": "user", "content": request.prompt})

        kwargs: dict[str, Any] = {
            "model": request.model,
            "messages": messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }
        if request.response_format:
            kwargs["response_format"] = request.response_format

        async def _call() -> Any:
            return await self._client.chat.completions.create(**kwargs)

        response = await retry_with_backoff(
            _call,
            is_retryable=_is_retryable,
            max_retries=self._max_retries,
            base_delay=self._base_backoff_seconds,
        )

        if not response.choices:
            raise ProviderResponseError("Groq returned no choices in response")
        choice = response.choices[0]
        text = choice.message.content or ""
        usage = response.usage
        return CompletionResponse(
            text=text,
            prompt_tokens=usage.prompt_tokens if usage else 0,
            completion_tokens=usage.completion_tokens if usage else 0,
            model=response.model,
            raw={
                "provider": "groq",
                "finish_reason": choice.finish_reason,
                "id": response.id,
            },
        )
