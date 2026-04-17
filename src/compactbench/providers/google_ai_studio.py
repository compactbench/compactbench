"""Google AI Studio provider (Gemini 2.0 Flash, etc.).

Requires ``compactbench[providers]`` (installs the ``google-genai`` SDK) and a
``COMPACTBENCH_GOOGLE_AI_STUDIO_API_KEY`` environment variable.
"""

from __future__ import annotations

import os
from typing import Any, ClassVar, cast

from compactbench.providers._retry import retry_with_backoff
from compactbench.providers.base import (
    CompletionRequest,
    CompletionResponse,
    Provider,
)
from compactbench.providers.errors import ProviderError


class GoogleAIStudioProvider(Provider):
    """Async Google AI Studio client (via the google-genai SDK)."""

    key: ClassVar[str] = "google-ai-studio"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        max_retries: int = 3,
        base_backoff_seconds: float = 2.0,
    ) -> None:
        try:
            from google import genai
        except ImportError as exc:
            raise ProviderError(
                "google-genai SDK is not installed. "
                "Install with: pip install 'compactbench[providers]'"
            ) from exc

        resolved_key = api_key or os.environ.get("COMPACTBENCH_GOOGLE_AI_STUDIO_API_KEY")
        if not resolved_key:
            raise ProviderError(
                "Google AI Studio API key required. Set "
                "COMPACTBENCH_GOOGLE_AI_STUDIO_API_KEY or pass api_key=."
            )

        self._client: Any = genai.Client(api_key=resolved_key)
        self._max_retries = max_retries
        self._base_backoff_seconds = base_backoff_seconds

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        from google.genai import errors as genai_errors
        from google.genai import types

        def _is_retryable(exc: Exception) -> bool:
            if not isinstance(exc, genai_errors.APIError):
                return False
            code = getattr(exc, "code", None)
            if code is None:
                code = getattr(exc, "status_code", None)
            if not isinstance(code, int):
                return False
            return code == 429 or code >= 500

        config_kwargs: dict[str, Any] = {
            "temperature": request.temperature,
            "max_output_tokens": request.max_tokens,
        }
        if request.system:
            config_kwargs["system_instruction"] = request.system
        if request.response_format and request.response_format.get("type") == "json_object":
            config_kwargs["response_mime_type"] = "application/json"
        config = types.GenerateContentConfig(**config_kwargs)

        async def _call() -> Any:
            return await self._client.aio.models.generate_content(
                model=request.model,
                contents=request.prompt,
                config=config,
            )

        response = await retry_with_backoff(
            _call,
            is_retryable=_is_retryable,
            max_retries=self._max_retries,
            base_delay=self._base_backoff_seconds,
        )

        text = getattr(response, "text", None) or ""
        usage_metadata = getattr(response, "usage_metadata", None)
        prompt_tokens = (
            (getattr(usage_metadata, "prompt_token_count", 0) or 0) if usage_metadata else 0
        )
        completion_tokens = (
            (getattr(usage_metadata, "candidates_token_count", 0) or 0) if usage_metadata else 0
        )
        raw_candidates = getattr(response, "candidates", None)
        candidates: list[Any] = (
            cast("list[Any]", raw_candidates) if isinstance(raw_candidates, list) else []
        )
        finish_reason = getattr(candidates[0], "finish_reason", None) if candidates else None
        return CompletionResponse(
            text=text,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            model=request.model,
            raw={
                "provider": "google-ai-studio",
                "finish_reason": str(finish_reason) if finish_reason is not None else None,
            },
        )
