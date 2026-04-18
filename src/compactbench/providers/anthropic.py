"""Anthropic provider (Claude 3.5 Sonnet, 3.5 Haiku, Opus 4, etc.).

Requires ``compactbench[providers]`` (installs the ``anthropic`` SDK) and a
``COMPACTBENCH_ANTHROPIC_API_KEY`` environment variable.
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


class AnthropicProvider(Provider):
    """Async Anthropic client with rate-limit + transient-error backoff."""

    key: ClassVar[str] = "anthropic"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        max_retries: int = 3,
        base_backoff_seconds: float = 2.0,
    ) -> None:
        try:
            from anthropic import AsyncAnthropic
        except ImportError as exc:
            raise ProviderError(
                "anthropic SDK is not installed. Install with: "
                "pip install 'compactbench[providers]'"
            ) from exc

        resolved_key = api_key or os.environ.get("COMPACTBENCH_ANTHROPIC_API_KEY")
        if not resolved_key:
            raise ProviderError(
                "Anthropic API key required. Set COMPACTBENCH_ANTHROPIC_API_KEY or pass api_key=."
            )

        self._client: Any = AsyncAnthropic(api_key=resolved_key)
        self._max_retries = max_retries
        self._base_backoff_seconds = base_backoff_seconds

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        from anthropic import (
            APIConnectionError,
            APITimeoutError,
            InternalServerError,
            RateLimitError,
        )

        def _is_retryable(exc: Exception) -> bool:
            return isinstance(
                exc,
                RateLimitError | APITimeoutError | APIConnectionError | InternalServerError,
            )

        # Anthropic takes `system` as a top-level kwarg, not a message role.
        kwargs: dict[str, Any] = {
            "model": request.model,
            "messages": [{"role": "user", "content": request.prompt}],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }
        if request.system:
            kwargs["system"] = request.system

        async def _call() -> Any:
            return await self._client.messages.create(**kwargs)

        response = await retry_with_backoff(
            _call,
            is_retryable=_is_retryable,
            max_retries=self._max_retries,
            base_delay=self._base_backoff_seconds,
        )

        content_blocks = getattr(response, "content", None) or []
        text_parts: list[str] = []
        for block in content_blocks:
            if getattr(block, "type", None) == "text":
                text_val = getattr(block, "text", "")
                if isinstance(text_val, str):
                    text_parts.append(text_val)
        if not text_parts:
            raise ProviderResponseError("Anthropic returned no text content blocks")

        usage = getattr(response, "usage", None)
        return CompletionResponse(
            text="".join(text_parts),
            prompt_tokens=getattr(usage, "input_tokens", 0) if usage else 0,
            completion_tokens=getattr(usage, "output_tokens", 0) if usage else 0,
            model=getattr(response, "model", request.model),
            raw={
                "provider": "anthropic",
                "id": getattr(response, "id", None),
                "stop_reason": getattr(response, "stop_reason", None),
            },
        )
