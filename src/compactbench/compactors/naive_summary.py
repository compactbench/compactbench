"""Naive summary baseline.

Single summarization call. Produces prose only — all ``structuredState``
sections remain empty. Intended as a floor baseline that structured methods
should outperform on retention metrics.
"""

from __future__ import annotations

from typing import Any, ClassVar

from compactbench.compactors._utils import fit_summary_text, render_transcript
from compactbench.compactors.base import Compactor
from compactbench.contracts import CompactionArtifact, StructuredState, Transcript
from compactbench.providers import CompletionRequest

_PROMPT = (
    "Summarize the following conversation in under 500 words. "
    "Preserve all constraints, decisions, unresolved tasks, and anything the "
    "user said must never happen.\n\n"
    "CONVERSATION:\n{transcript}\n\n"
    "SUMMARY:"
)


class NaiveSummaryCompactor(Compactor):
    """Baseline: one call, prose only, no structured state."""

    name: ClassVar[str] = "naive-summary"
    version: ClassVar[str] = "1.0.0"

    async def compact(
        self,
        transcript: Transcript,
        config: dict[str, Any] | None = None,
        previous_artifact: CompactionArtifact | None = None,
    ) -> CompactionArtifact:
        prompt = _PROMPT.format(transcript=render_transcript(transcript))
        response = await self.provider.complete(CompletionRequest(model=self.model, prompt=prompt))
        summary, length_warnings = fit_summary_text(response.text.strip())
        return CompactionArtifact(
            summaryText=summary,
            structured_state=StructuredState(),
            selectedSourceTurnIds=[t.id for t in transcript.turns],
            warnings=length_warnings,
            methodMetadata={
                "method": self.name,
                "version": self.version,
                "model": self.model,
                "provider": self.provider.key,
                "calls": 1,
                "prompt_tokens": response.prompt_tokens,
                "completion_tokens": response.completion_tokens,
            },
        )
