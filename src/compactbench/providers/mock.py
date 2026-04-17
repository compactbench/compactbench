"""Deterministic mock provider for tests and offline development.

``MockProvider`` can be used in two modes:

- **Scripted sequence** — pass ``responses=[...]`` to get the given texts back
  in order. After the list is exhausted, returns ``default``.
- **Single default** — pass only ``default="..."`` to always return the same
  string.

Every call is recorded in ``provider.calls`` for inspection in tests.
"""

from __future__ import annotations

from typing import ClassVar

from compactbench.providers.base import CompletionRequest, CompletionResponse, Provider


class MockProvider(Provider):
    """Provider that returns canned responses without touching the network."""

    key: ClassVar[str] = "mock"

    def __init__(
        self,
        responses: list[str] | None = None,
        default: str = "",
    ) -> None:
        self._responses: list[str] = list(responses or [])
        self._default: str = default
        self._index: int = 0
        self.calls: list[CompletionRequest] = []

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        self.calls.append(request)
        if self._index < len(self._responses):
            text = self._responses[self._index]
            self._index += 1
        else:
            text = self._default
        return CompletionResponse(
            text=text,
            prompt_tokens=max(1, len(request.prompt) // 4),
            completion_tokens=max(1, len(text) // 4),
            model=request.model,
            raw={"provider": "mock", "call_index": len(self.calls) - 1},
        )

    def reset(self) -> None:
        """Reset the scripted-response pointer and clear recorded calls."""
        self._index = 0
        self.calls.clear()
