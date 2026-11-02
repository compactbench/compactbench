"""Hierarchical summary: chunk new turns -> per-chunk summary -> merged summary -> state."""

from __future__ import annotations

from typing import ClassVar

from compactbench.compactors._state_parser import parse_state
from compactbench.compactors._utils import (
    budget_instruction,
    chunk,
    finalize,
    fit_summary_text,
    output_tokens,
    reasoning_effort,
)
from compactbench.compactors.base import Compactor
from compactbench.contracts import CompactionArtifact, CompactionRequest
from compactbench.providers import CompletionRequest
from compactbench.rendering import render_turns

_CHUNK_PROMPT = (
    "Summarize these {n} conversation turns in under 200 words. Preserve rules, "
    "decisions (and what they replaced), owners, open tasks, and exact numbers, "
    "dates and identifiers.\n\n"
    "TURNS:\n{turns}\n\n"
    "SUMMARY:"
)

_MERGE_PROMPT = (
    "Merge the earlier summary with the summaries of newer conversation segments "
    "into one up-to-date summary. Where a newer segment changes something, keep "
    "the newer version and note what it replaced. {length}\n\n"
    "EARLIER SUMMARY:\n{previous}\n\n"
    "NEWER SEGMENTS:\n{segments}\n\n"
    "MERGED SUMMARY:"
)

_STATE_PROMPT = (
    "Extract a strict JSON object with the current state described by this "
    "summary. Return ONLY the JSON, no prose.\n\n"
    "Required fields: immutable_facts, locked_decisions, deferred_items, "
    "forbidden_behaviors, entity_map, unresolved_items.\n\n"
    "SUMMARY:\n{summary}\n\n"
    "JSON:"
)


class HierarchicalSummaryCompactor(Compactor):
    """Two-level summarization plus a structured-state extraction call."""

    name: ClassVar[str] = "hierarchical-summary"
    version: ClassVar[str] = "2.0.0"

    _CHUNK_SIZE: ClassVar[int] = 12
    _SUMMARY_SHARE: ClassVar[float] = 0.6

    async def compact(self, request: CompactionRequest) -> CompactionArtifact:
        prompt_tokens = 0
        completion_tokens = 0
        calls = 0

        chunk_summaries: list[str] = []
        for turns in chunk(list(request.turns), self._CHUNK_SIZE):
            response = await self.provider.complete(
                CompletionRequest(
                    model=self.model,
                    prompt=_CHUNK_PROMPT.format(n=len(turns), turns=render_turns(turns)),
                    max_tokens=output_tokens(request),
                    reasoning_effort=reasoning_effort(self.config),
                )
            )
            chunk_summaries.append(response.text.strip())
            prompt_tokens += response.prompt_tokens
            completion_tokens += response.completion_tokens
            calls += 1

        previous = (
            request.previous_artifact.summary_text.strip()
            if request.previous_artifact is not None
            else ""
        )
        if not previous and len(chunk_summaries) == 1:
            # A short first cycle has nothing to merge; skip the extra call.
            summary, length_warnings = fit_summary_text(chunk_summaries[0])
        else:
            merge = await self.provider.complete(
                CompletionRequest(
                    model=self.model,
                    prompt=_MERGE_PROMPT.format(
                        length=budget_instruction(request, share=self._SUMMARY_SHARE),
                        previous=previous or "(none — this is the start of the conversation)",
                        segments="\n\n".join(
                            f"SEGMENT {i + 1}: {s}" for i, s in enumerate(chunk_summaries)
                        )
                        or "(no new turns)",
                    ),
                    max_tokens=output_tokens(request),
                    reasoning_effort=reasoning_effort(self.config),
                )
            )
            summary, length_warnings = fit_summary_text(merge.text.strip())
            prompt_tokens += merge.prompt_tokens
            completion_tokens += merge.completion_tokens
            calls += 1

        state_response = await self.provider.complete(
            CompletionRequest(
                model=self.model,
                prompt=_STATE_PROMPT.format(summary=summary),
                response_format={"type": "json_object"},
                max_tokens=output_tokens(request),
                reasoning_effort=reasoning_effort(self.config),
            )
        )
        state, warnings = parse_state(state_response.text)
        prompt_tokens += state_response.prompt_tokens
        completion_tokens += state_response.completion_tokens
        calls += 1

        artifact = CompactionArtifact(
            summaryText=summary,
            structured_state=state,
            selectedSourceTurnIds=[t.id for t in request.turns],
            warnings=[*warnings, *length_warnings],
            methodMetadata={
                "method": self.name,
                "version": self.version,
                "model": self.model,
                "provider": self.provider.key,
                "chunks": len(chunk_summaries),
                "calls": calls,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
            },
        )
        return finalize(artifact, request)
