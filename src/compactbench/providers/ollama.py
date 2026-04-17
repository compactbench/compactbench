"""Ollama local provider.

Requires ``compactbench[providers]`` (installs the ``ollama`` SDK). Connects to
a local or remote Ollama server via ``COMPACTBENCH_OLLAMA_BASE_URL`` (default
``http://localhost:11434``).
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
from compactbench.providers.errors import ProviderError


class OllamaProvider(Provider):
    """Async Ollama client (runs models locally)."""

    key: ClassVar[str] = "ollama"

    def __init__(
        self,
        *,
        base_url: str | None = None,
        max_retries: int = 3,
        base_backoff_seconds: float = 1.0,
    ) -> None:
        try:
            from ollama import AsyncClient
        except ImportError as exc:
            raise ProviderError(
                "ollama SDK is not installed. Install with: pip install 'compactbench[providers]'"
            ) from exc

        resolved_url = base_url or os.environ.get(
            "COMPACTBENCH_OLLAMA_BASE_URL", "http://localhost:11434"
        )
        self._client: Any = AsyncClient(host=resolved_url)
        self._max_retries = max_retries
        self._base_backoff_seconds = base_backoff_seconds

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        import httpx
        from ollama import ResponseError

        def _is_retryable(exc: Exception) -> bool:
            if isinstance(exc, httpx.TimeoutException | httpx.ConnectError):
                return True
            if isinstance(exc, ResponseError):
                code = getattr(exc, "status_code", None)
                return isinstance(code, int) and (code == 429 or code >= 500)
            return False

        messages: list[dict[str, str]] = []
        if request.system:
            messages.append({"role": "system", "content": request.system})
        messages.append({"role": "user", "content": request.prompt})

        chat_kwargs: dict[str, Any] = {
            "model": request.model,
            "messages": messages,
            "options": {
                "temperature": request.temperature,
                "num_predict": request.max_tokens,
            },
        }
        if request.response_format and request.response_format.get("type") == "json_object":
            chat_kwargs["format"] = "json"

        async def _call() -> Any:
            return await self._client.chat(**chat_kwargs)

        response = await retry_with_backoff(
            _call,
            is_retryable=_is_retryable,
            max_retries=self._max_retries,
            base_delay=self._base_backoff_seconds,
        )

        message = response.message
        text = getattr(message, "content", None) or ""
        prompt_tokens = getattr(response, "prompt_eval_count", 0) or 0
        completion_tokens = getattr(response, "eval_count", 0) or 0

        return CompletionResponse(
            text=text,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            model=request.model,
            raw={
                "provider": "ollama",
                "done_reason": getattr(response, "done_reason", None),
            },
        )
