"""Naive summary baseline.

One summarization call per cycle that rewrites the running summary from the
previous summary plus the new turns. Prose only — every ``structuredState``
section stays empty. The floor that structured methods should beat.
"""

from __future__ import annotations

from typing import ClassVar

from compactbench.compactors._utils import (
    budget_instruction,
    finalize,
    fit_summary_text,
    output_tokens,
    reasoning_effort,
)
from compactbench.compactors.base import Compactor
from compactbench.contracts import CompactionArtifact, CompactionRequest, StructuredState
from compactbench.providers import CompletionRequest
from compactbench.rendering import render_request

_PROMPT = (
    "You maintain the memory of a long-running conversation. The text below "
    "will be replaced by your summary, so anything you leave out is lost.\n\n"
    "{body}\n\n"
    "Write an updated summary of the whole conversation so far. Preserve every "
    "rule and constraint, every decision (and what it replaced), who owns or "
    "decided what, open tasks, and exact numbers, dates and identifiers. "
    "{length}\n\n"
    "SUMMARY:"
)


class NaiveSummaryCompactor(Compactor):
    """Baseline: one call, prose only, no structured state."""

    name: ClassVar[str] = "naive-summary"
    version: ClassVar[str] = "2.0.0"

    async def compact(self, request: CompactionRequest) -> CompactionArtifact:
        prompt = _PROMPT.format(body=render_request(request), length=budget_instruction(request))
        response = await self.provider.complete(
            CompletionRequest(
                model=self.model,
                prompt=prompt,
                max_tokens=output_tokens(request),
                reasoning_effort=reasoning_effort(self.config),
            )
        )
        summary, length_warnings = fit_summary_text(response.text.strip())
        artifact = CompactionArtifact(
            summaryText=summary,
            structured_state=StructuredState(),
            selectedSourceTurnIds=[t.id for t in request.turns],
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
        return finalize(artifact, request)
