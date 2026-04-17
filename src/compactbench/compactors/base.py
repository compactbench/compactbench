"""Compactor ABC.

Every built-in and external compaction method subclasses this and returns a
validated :class:`CompactionArtifact`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from compactbench.contracts import CompactionArtifact, Transcript


class Compactor(ABC):
    """Abstract base for compaction methods."""

    name: str
    version: str

    @abstractmethod
    def compact(
        self,
        transcript: Transcript,
        config: dict[str, Any] | None = None,
        previous_artifact: CompactionArtifact | None = None,
    ) -> CompactionArtifact:
        """Produce a compacted artifact from a transcript.

        ``previous_artifact`` is provided on drift cycles so ledger-style methods
        can accumulate state; stateless methods should ignore it.
        """
