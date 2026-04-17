"""Your compaction method.

Replace ``MyCompactor`` with your own class name and implement ``compact``.
Run ``compactbench run --method submissions/<your-handle>/<name>/method.py:MyCompactor
--suite elite_practice`` locally before opening a PR.

Full API docs: https://compactbench.github.io/compactbench/writing-a-compactor/
"""

from __future__ import annotations

from typing import Any, ClassVar

from compactbench.compactors import Compactor
from compactbench.contracts import CompactionArtifact, StructuredState, Transcript
from compactbench.providers import CompletionRequest


class MyCompactor(Compactor):
    """One-line description of what your method does.

    Longer description: what's novel, what tradeoffs you're making, what you
    expect to score well on.
    """

    name: ClassVar[str] = "my-method"  # change to your method's key
    version: ClassVar[str] = "0.1.0"

    async def compact(
        self,
        transcript: Transcript,
        config: dict[str, Any] | None = None,
        previous_artifact: CompactionArtifact | None = None,
    ) -> CompactionArtifact:
        # TODO: implement. The example below is a stub — replace with your logic.
        rendered = "\n\n".join(f"{t.role.value.upper()}: {t.content}" for t in transcript.turns)
        response = await self.provider.complete(
            CompletionRequest(
                model=self.model,
                prompt=(
                    "Summarize the conversation below, preserving every constraint and decision:\n\n"
                    f"{rendered}"
                ),
            )
        )
        return CompactionArtifact(
            summaryText=response.text.strip(),
            structured_state=StructuredState(),
            selectedSourceTurnIds=[t.id for t in transcript.turns],
            warnings=[],
            methodMetadata={
                "method": self.name,
                "version": self.version,
                "model": self.model,
                "provider": self.provider.key,
                "calls": 1,
            },
        )
