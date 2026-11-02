"""Anthropic provider (Claude Opus 5.5, Sonnet 5.5, Haiku 5.5, etc.).

Requires ``compactbench[providers]`` (installs the ``anthropic`` SDK) and a
``COMPACTBENCH_ANTHROPIC_API_KEY`` environment variable.

The ``anthropic`` 2.x SDK sends API version ``2026-10-21``, which rejects
``temperature``, ``top_p`` and ``top_k`` on every model with a 400. This
provider therefore never sends a sampling parameter, whatever the request
says: ``CompletionRequest.temperature`` is ignored here.
"""

from __future__ import annotations

import os
from typing import Any, ClassVar

from compactbench.contracts import TokenUsage
from compactbench.providers._retry import is_terminal_quota_error, retry_with_backoff
from compactbench.providers.base import (
    CompletionRequest,
    CompletionResponse,
    Provider,
)
from compactbench.providers.errors import ProviderError, ProviderResponseError

# Current Claude models (Haiku 5.5, Sonnet 5.5, Opus 5.5) run adaptive thinking
# by default, and thinking tokens count toward ``max_tokens``. A cap sized for
# the visible answer alone can be spent entirely on thinking, ending the turn
# with ``stop_reason == "max_tokens"`` and no text. Anthropic's Haiku 5.5
# migration guide gives even a one-word classification route 1024 tokens of
# "room for thinking plus the answer", so never send a smaller cap. The cap is
# a ceiling, not a charge: billing follows the tokens actually generated.
MIN_MAX_TOKENS = 1024
#: Beta header for on-demand server-side compaction.
COMPACTION_BETA = "compact-2026-09-04"


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

    @staticmethod
    def _is_retryable(exc: Exception) -> bool:
        from anthropic import (
            APIConnectionError,
            APITimeoutError,
            DeadlineExceededError,
            InternalServerError,
            OverloadedError,
            RateLimitError,
            ServiceUnavailableError,
        )

        if isinstance(exc, RateLimitError) and is_terminal_quota_error(exc):
            return False
        # The SDK maps 529 to OverloadedError (and has 503/504 classes),
        # none of which subclass InternalServerError, so name them all.
        return isinstance(
            exc,
            RateLimitError
            | APITimeoutError
            | APIConnectionError
            | InternalServerError
            | OverloadedError
            | ServiceUnavailableError
            | DeadlineExceededError,
        )

    async def summarize(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        max_tokens: int,
        instructions: str | None = None,
    ) -> tuple[dict[str, Any], TokenUsage]:
        """Server-side on-demand compaction (beta ``compact-2026-09-04``).

        Returns the ``compaction`` block exactly as the API sent it (send it back
        first in ``messages`` to compact again) and the usage, summed across
        ``usage.iterations`` because the top-level counts are zero on a
        compaction call.
        """
        compaction: dict[str, Any] = {"type": "summarize"}
        if instructions:
            compaction["instructions"] = instructions

        async def _call() -> Any:
            return await self._client.beta.messages.create(
                model=model,
                max_tokens=max(max_tokens, MIN_MAX_TOKENS),
                betas=[COMPACTION_BETA],
                messages=messages,
                compaction=compaction,
            )

        response = await retry_with_backoff(
            _call,
            is_retryable=self._is_retryable,
            max_retries=self._max_retries,
            base_delay=self._base_backoff_seconds,
        )
        stop_reason: Any = getattr(response, "stop_reason", None)
        blocks: list[Any] = getattr(response, "content", None) or []
        block = next((b for b in blocks if getattr(b, "type", None) == "compaction"), None)
        if block is None:
            raise ProviderResponseError(
                f"Anthropic returned no compaction block (stop_reason={stop_reason!r})"
            )
        usage = getattr(response, "usage", None)
        iterations: list[Any] = list(getattr(usage, "iterations", None) or [])
        prompt_tokens = sum(int(getattr(i, "input_tokens", 0) or 0) for i in iterations)
        completion_tokens = sum(int(getattr(i, "output_tokens", 0) or 0) for i in iterations)
        payload: dict[str, Any] = block.to_dict()
        return payload, TokenUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            call_count=1,
        )

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        # Anthropic takes `system` as a top-level kwarg, not a message role.
        # When the caller supplies a cached_prefix we split the user message
        # into two content blocks and mark the prefix with `cache_control`
        # ephemeral — subsequent calls that reuse the same prefix get ~90%
        # off its input-token cost. Without the prefix we send the simpler
        # single-string content the Messages API also accepts.
        user_content: Any
        if request.cached_prefix:
            user_content = [
                {
                    "type": "text",
                    "text": request.cached_prefix,
                    "cache_control": {"type": "ephemeral"},
                },
                {"type": "text", "text": request.prompt},
            ]
        else:
            user_content = request.prompt

        max_tokens = max(request.max_tokens, MIN_MAX_TOKENS)
        # No `temperature`: see the module docstring.
        kwargs: dict[str, Any] = {
            "model": request.model,
            "messages": [{"role": "user", "content": user_content}],
            "max_tokens": max_tokens,
        }
        if request.system:
            kwargs["system"] = request.system

        # Structured outputs and effort both live under `output_config`. The
        # Messages API has no schema-less JSON mode, so a bare
        # `response_format={"type": "json_object"}` is left to the prompt and
        # the caller's validation.
        output_config: dict[str, Any] = {}
        if request.json_schema is not None:
            output_config["format"] = {"type": "json_schema", "schema": request.json_schema}
        if request.reasoning_effort is not None:
            output_config["effort"] = request.reasoning_effort
        if output_config:
            kwargs["output_config"] = output_config

        async def _call() -> Any:
            return await self._client.messages.create(**kwargs)

        response = await retry_with_backoff(
            _call,
            is_retryable=self._is_retryable,
            max_retries=self._max_retries,
            base_delay=self._base_backoff_seconds,
        )

        stop_reason: Any = getattr(response, "stop_reason", None)
        if stop_reason == "refusal":
            # A safety-classifier or model decline is an HTTP 200; any partial
            # text is not an answer. `stop_details` may be null even here.
            stop_details: Any = getattr(response, "stop_details", None)
            category: Any = getattr(stop_details, "category", None) if stop_details else None
            raise ProviderResponseError(
                f"Anthropic declined the request (stop_reason='refusal', category={category!r})"
            )

        # Read blocks by type: thinking blocks (empty text by default) can come
        # before the answer and are not part of it.
        content_blocks: list[Any] = getattr(response, "content", None) or []
        text_parts: list[str] = []
        for block in content_blocks:
            block_type: Any = getattr(block, "type", None)
            if block_type == "text":
                text_val: Any = getattr(block, "text", "")
                if isinstance(text_val, str):
                    text_parts.append(text_val)
        text = "".join(text_parts)
        if not text and stop_reason == "max_tokens":
            raise ProviderResponseError(
                f"Anthropic stopped at max_tokens={max_tokens} before writing any text; "
                "thinking likely used the whole budget. Raise max_tokens or lower "
                "reasoning_effort."
            )
        if not text_parts:
            raise ProviderResponseError("Anthropic returned no text content blocks")

        usage = getattr(response, "usage", None)
        # Anthropic reports cache hits under ``cache_read_input_tokens`` and
        # newly-written cache entries under ``cache_creation_input_tokens``;
        # we surface both in ``raw`` so downstream telemetry can distinguish
        # a cheap cached call from a full-price first call on the same prefix.
        cache_read = getattr(usage, "cache_read_input_tokens", 0) if usage else 0
        cache_creation = getattr(usage, "cache_creation_input_tokens", 0) if usage else 0
        return CompletionResponse(
            text=text,
            prompt_tokens=getattr(usage, "input_tokens", 0) if usage else 0,
            completion_tokens=getattr(usage, "output_tokens", 0) if usage else 0,
            model=getattr(response, "model", request.model),
            raw={
                "provider": "anthropic",
                "id": getattr(response, "id", None),
                "stop_reason": stop_reason,
                "cache_read_input_tokens": cache_read or 0,
                "cache_creation_input_tokens": cache_creation or 0,
            },
        )
