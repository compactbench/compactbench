"""Hierarchical summary: chunk -> per-chunk summary -> meta-summary -> structured state."""

from __future__ import annotations

from typing import Any, ClassVar

from compactbench.compactors._state_parser import parse_state
from compactbench.compactors._utils import chunk, render_transcript, render_turns
from compactbench.compactors.base import Compactor
from compactbench.contracts import CompactionArtifact, Transcript
from compactbench.providers import CompletionRequest

_CHUNK_PROMPT = (
    "Summarize these {n} conversation turns in under 200 words. Preserve "
    "constraints, decisions, and unresolved items.\n\n"
    "TURNS:\n{turns}\n\n"
    "SUMMARY:"
)

_META_PROMPT = (
    "Combine these partial summaries into one coherent summary in under 500 "
    "words. Preserve every constraint, decision, and unresolved item.\n\n"
    "{summaries}\n\n"
    "FINAL SUMMARY:"
)

_STATE_PROMPT = (
    "Extract a strict JSON object summarizing the state of this conversation. "
    "Return ONLY the JSON, no prose.\n\n"
    "Required fields: immutable_facts, locked_decisions, deferred_items, "
    "forbidden_behaviors, entity_map, unresolved_items.\n\n"
    "CONVERSATION:\n{transcript}\n\n"
    "JSON:"
)


class HierarchicalSummaryCompactor(Compactor):
    """Two-level summarization plus a separate structured-state extraction call."""

    name: ClassVar[str] = "hierarchical-summary"
    version: ClassVar[str] = "1.0.0"

    _CHUNK_SIZE: ClassVar[int] = 10

    async def compact(
        self,
        transcript: Transcript,
        config: dict[str, Any] | None = None,
        previous_artifact: CompactionArtifact | None = None,
    ) -> CompactionArtifact:
        chunks = chunk(list(transcript.turns), self._CHUNK_SIZE)

        chunk_summaries: list[str] = []
        total_prompt_tokens = 0
        total_completion_tokens = 0

        for turns in chunks:
            response = await self.provider.complete(
                CompletionRequest(
                    model=self.model,
                    prompt=_CHUNK_PROMPT.format(n=len(turns), turns=render_turns(turns)),
                )
            )
            chunk_summaries.append(response.text.strip())
            total_prompt_tokens += response.prompt_tokens
            total_completion_tokens += response.completion_tokens

        if len(chunk_summaries) == 1:
            final_summary = chunk_summaries[0]
        else:
            meta_response = await self.provider.complete(
                CompletionRequest(
                    model=self.model,
                    prompt=_META_PROMPT.format(
                        summaries="\n\n".join(
                            f"PARTIAL {i + 1}: {s}" for i, s in enumerate(chunk_summaries)
                        )
                    ),
                )
            )
            final_summary = meta_response.text.strip()
            total_prompt_tokens += meta_response.prompt_tokens
            total_completion_tokens += meta_response.completion_tokens

        state_response = await self.provider.complete(
            CompletionRequest(
                model=self.model,
                prompt=_STATE_PROMPT.format(transcript=render_transcript(transcript)),
                response_format={"type": "json_object"},
            )
        )
        state, warnings = parse_state(state_response.text)
        total_prompt_tokens += state_response.prompt_tokens
        total_completion_tokens += state_response.completion_tokens

        total_calls = len(chunk_summaries) + (1 if len(chunk_summaries) > 1 else 0) + 1

        return CompactionArtifact(
            summaryText=final_summary,
            structured_state=state,
            selectedSourceTurnIds=[t.id for t in transcript.turns],
            warnings=warnings,
            methodMetadata={
                "method": self.name,
                "version": self.version,
                "model": self.model,
                "provider": self.provider.key,
                "chunks": len(chunks),
                "calls": total_calls,
                "prompt_tokens": total_prompt_tokens,
                "completion_tokens": total_completion_tokens,
            },
        )
