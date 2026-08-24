"""OpenAI provider (GPT-4o, GPT-4o-mini, o1, etc.).

Requires ``compactbench[providers]`` (installs the ``openai`` SDK) and a
``COMPACTBENCH_OPENAI_API_KEY`` environment variable.

Also serves any **OpenAI-compatible** endpoint via ``COMPACTBENCH_OPENAI_BASE_URL``
— vLLM, llama.cpp's server, LM Studio, Together, Fireworks, OpenRouter and friends
all speak the same ``/v1/chat/completions`` wire format, so they need a URL rather
than a new provider. When a base URL is set the API key becomes optional, because
self-hosted servers generally do not check one.
"""

from __future__ import annotations

import os
from typing import Any, ClassVar

from compactbench.providers._retry import is_terminal_quota_error, retry_with_backoff
from compactbench.providers.base import (
    CompletionRequest,
    CompletionResponse,
    Provider,
)
from compactbench.providers.errors import ProviderError, ProviderResponseError


class OpenAIProvider(Provider):
    """Async OpenAI client with rate-limit + transient-error backoff."""

    key: ClassVar[str] = "openai"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        max_retries: int = 3,
        base_backoff_seconds: float = 2.0,
    ) -> None:
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise ProviderError(
                "openai SDK is not installed. Install with: pip install 'compactbench[providers]'"
            ) from exc

        resolved_url = base_url or os.environ.get("COMPACTBENCH_OPENAI_BASE_URL")
        resolved_key = api_key or os.environ.get("COMPACTBENCH_OPENAI_API_KEY")
        if not resolved_key:
            if not resolved_url:
                raise ProviderError(
                    "OpenAI API key required. Set COMPACTBENCH_OPENAI_API_KEY or pass api_key=."
                )
            # A self-hosted OpenAI-compatible server usually ignores the key, but the
            # SDK still refuses to construct without one. Requiring a real key here
            # would make the base-url path unusable for the local-model case it exists
            # to serve; a hosted gateway that *does* check will reject this and say so.
            resolved_key = "not-required"

        kwargs: dict[str, Any] = {"api_key": resolved_key}
        if resolved_url:
            kwargs["base_url"] = resolved_url
        self._client: Any = AsyncOpenAI(**kwargs)
        self._base_url = resolved_url
        self._max_retries = max_retries
        self._base_backoff_seconds = base_backoff_seconds

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        from openai import APIConnectionError, APITimeoutError, InternalServerError, RateLimitError

        def _is_retryable(exc: Exception) -> bool:
            if isinstance(exc, RateLimitError) and is_terminal_quota_error(exc):
                return False
            return isinstance(
                exc,
                RateLimitError | APITimeoutError | APIConnectionError | InternalServerError,
            )

        # OpenAI's automatic prompt caching kicks in for stable prefixes >=
        # 1024 tokens at the start of a message, so prepending cached_prefix
        # to the user content is all we need — no explicit cache API.
        user_content = (
            request.cached_prefix + request.prompt if request.cached_prefix else request.prompt
        )

        messages: list[dict[str, str]] = []
        if request.system:
            messages.append({"role": "system", "content": request.system})
        messages.append({"role": "user", "content": user_content})

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

        choices: list[Any] = getattr(response, "choices", None) or []
        if not choices:
            raise ProviderResponseError("OpenAI returned no choices in response")
        choice: Any = choices[0]
        message: Any = getattr(choice, "message", None)
        text_raw: Any = getattr(message, "content", None) or ""
        text = text_raw if isinstance(text_raw, str) else ""
        usage: Any = getattr(response, "usage", None)
        # OpenAI reports automatic-cache hits nested under
        # ``usage.prompt_tokens_details.cached_tokens``. Surface it in ``raw``
        # so the counting wrapper can tell first-call (full price) from
        # reused-prefix (~50% discount) calls.
        prompt_details: Any = getattr(usage, "prompt_tokens_details", None) if usage else None
        cached_tokens_val = (
            getattr(prompt_details, "cached_tokens", 0) if prompt_details is not None else 0
        )
        cached_tokens = int(cached_tokens_val) if cached_tokens_val else 0
        return CompletionResponse(
            text=text,
            prompt_tokens=getattr(usage, "prompt_tokens", 0) if usage else 0,
            completion_tokens=getattr(usage, "completion_tokens", 0) if usage else 0,
            model=getattr(response, "model", request.model),
            raw={
                "provider": "openai",
                "finish_reason": getattr(choice, "finish_reason", None),
                "id": getattr(response, "id", None),
                "cached_tokens": cached_tokens,
                # Provenance without disclosure: a leaderboard reviewer needs to know
                # a run did not go to OpenAI, but the URL itself is often an internal
                # host and results files get shared, so record only that it differed.
                "custom_base_url": self._base_url is not None,
            },
        )
