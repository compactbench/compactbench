"""Compactor ABC.

Every built-in and external compaction method subclasses this and returns a
validated :class:`CompactionArtifact`. A compactor is bound to a provider +
model at construction; ``compact`` is async because provider calls are.
"""

from __future__ import annotations

import inspect
from abc import ABC, abstractmethod
from typing import Any, ClassVar

from compactbench.contracts import CompactionArtifact, CompactionRequest
from compactbench.providers import Provider

_MIGRATION_HINT = (
    "CompactBench 0.3 changed the compactor interface to "
    "`async def compact(self, request: CompactionRequest) -> CompactionArtifact`. "
    "`request.turns` holds only the turns since the last compaction and "
    "`request.previous_artifact` holds your previous output. "
    "See docs/writing-a-compactor.md#migrating-from-02."
)


class Compactor(ABC):
    """Abstract base for compaction methods.

    ``provider`` / ``model`` are what the method uses for its own LLM calls.
    The reader that answers probes afterwards is configured separately by the
    runner, so methods are free to use any model they like.
    """

    name: ClassVar[str]
    version: ClassVar[str]

    def __init__(
        self,
        provider: Provider,
        model: str,
        config: dict[str, Any] | None = None,
    ) -> None:
        self.provider = provider
        self.model = model
        self.config: dict[str, Any] = dict(config or {})

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        compact = cls.__dict__.get("compact")
        if compact is not None and "transcript" in inspect.signature(compact).parameters:
            raise TypeError(f"{cls.__name__}.compact uses the 0.2 signature. {_MIGRATION_HINT}")

    @abstractmethod
    async def compact(self, request: CompactionRequest) -> CompactionArtifact:
        """Produce the artifact that replaces everything the method has seen so far."""

    async def aclose(self) -> None:  # noqa: B027 - optional hook, deliberately empty
        """Release anything held for the case. The runner calls it once the case ends."""
