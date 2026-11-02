"""Sectioned summary baseline: the format coding agents commonly compact into.

One call per cycle that rewrites a summary under fixed headings — the request,
decisions, people, facts, tasks, open questions and current state — from the
previous summary plus the new turns. The prompt is generic: it asks for a good
working summary, not for the specific things the benchmark probes.
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
    "Your context window is being compacted. Write a summary of the conversation so far "
    "that would let you continue the work without the original messages.\n\n"
    "{body}\n\n"
    "Use these sections:\n"
    "1. Primary request and intent\n"
    "2. Key decisions and constraints\n"
    "3. People and responsibilities\n"
    "4. Important facts and figures\n"
    "5. Tasks (done, in progress, pending)\n"
    "6. Open questions\n"
    "7. Current state and next step\n\n"
    "{length}\n\n"
    "SUMMARY:"
)


class SectionedSummaryCompactor(Compactor):
    """Baseline: one call, a generic sectioned summary, no structured state."""

    name: ClassVar[str] = "sectioned-summary"
    version: ClassVar[str] = "1.0.0"

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
