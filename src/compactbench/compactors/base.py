"""Compactor ABC.

Every built-in and external compaction method subclasses this and returns a
validated :class:`CompactionArtifact`. A compactor is bound to a provider +
model at construction; ``compact`` is async because provider calls are.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, ClassVar

from compactbench.contracts import CompactionArtifact, Transcript
from compactbench.providers import Provider


class Compactor(ABC):
    """Abstract base for compaction methods."""

    name: ClassVar[str]
    version: ClassVar[str]

    def __init__(self, provider: Provider, model: str) -> None:
        self.provider = provider
        self.model = model

    @abstractmethod
    async def compact(
        self,
        transcript: Transcript,
        config: dict[str, Any] | None = None,
        previous_artifact: CompactionArtifact | None = None,
    ) -> CompactionArtifact:
        """Produce a compacted artifact from a transcript.

        ``previous_artifact`` is provided on drift cycles so ledger-style methods
        can accumulate state; stateless methods should ignore it.
        """
