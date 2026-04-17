"""Your compaction method.

This file ships as a working example — it compiles, runs, and produces a valid
artifact out of the box (a naive summary). Your job is to replace the body of
``compact`` with something better and rename the class + ``name`` to match.

Before opening a PR, run locally:

    compactbench run \\
        --method submissions/HANDLE/METHOD_NAME/method.py:MyCompactor \\
        --suite elite_practice \\
        --provider ollama --model llama3.2

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

    name: ClassVar[str] = "my-method"
    version: ClassVar[str] = "0.1.0"

    async def compact(
        self,
        transcript: Transcript,
        config: dict[str, Any] | None = None,
        previous_artifact: CompactionArtifact | None = None,
    ) -> CompactionArtifact:
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
