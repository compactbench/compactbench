"""Hybrid ledger: append-only structured state across cycles + short prose header."""

from __future__ import annotations

from typing import Any, ClassVar

from compactbench.compactors._state_parser import parse_state
from compactbench.compactors._utils import render_transcript, uniq_preserve_order
from compactbench.compactors.base import Compactor
from compactbench.contracts import CompactionArtifact, StructuredState, Transcript
from compactbench.providers import CompletionRequest

_DELTA_PROMPT = (
    "Extract NEW state that appears in this conversation segment as a strict "
    "JSON object. Include only items stated or decided in these turns; do not "
    "infer beyond the text. Return ONLY the JSON, no prose.\n\n"
    "Required fields: immutable_facts, locked_decisions, deferred_items, "
    "forbidden_behaviors, entity_map, unresolved_items.\n\n"
    "CONVERSATION:\n{transcript}\n\n"
    "JSON:"
)

_HEADER_PROMPT = (
    "Write a 2-to-3 sentence header describing the current situation. "
    "Do not restate constraints or decisions (they are tracked separately). "
    "Focus on: what is being worked on, who is involved, what phase we are in.\n\n"
    "CONVERSATION:\n{transcript}\n\n"
    "HEADER:"
)


class HybridLedgerCompactor(Compactor):
    """Append-only ledger compactor.

    - ``locked_decisions``, ``forbidden_behaviors``, ``deferred_items``,
      ``unresolved_items`` accumulate across cycles (de-duplicated).
    - ``immutable_facts`` and ``entity_map`` are re-extracted each cycle.
    - ``summaryText`` is a short (2-3 sentence) situational header.
    """

    name: ClassVar[str] = "hybrid-ledger"
    version: ClassVar[str] = "1.0.0"

    async def compact(
        self,
        transcript: Transcript,
        config: dict[str, Any] | None = None,
        previous_artifact: CompactionArtifact | None = None,
    ) -> CompactionArtifact:
        delta_response = await self.provider.complete(
            CompletionRequest(
                model=self.model,
                prompt=_DELTA_PROMPT.format(transcript=render_transcript(transcript)),
                response_format={"type": "json_object"},
            )
        )
        delta, warnings = parse_state(delta_response.text)

        header_response = await self.provider.complete(
            CompletionRequest(
                model=self.model,
                prompt=_HEADER_PROMPT.format(transcript=render_transcript(transcript)),
            )
        )
        header = header_response.text.strip()

        merged = _merge_ledger(delta, previous_artifact)
        cycles_accumulated = _cycles_accumulated(previous_artifact)

        return CompactionArtifact(
            summaryText=header,
            structured_state=merged,
            selectedSourceTurnIds=[t.id for t in transcript.turns],
            warnings=warnings,
            methodMetadata={
                "method": self.name,
                "version": self.version,
                "model": self.model,
                "provider": self.provider.key,
                "calls": 2,
                "cycles_accumulated": cycles_accumulated,
                "prompt_tokens": delta_response.prompt_tokens + header_response.prompt_tokens,
                "completion_tokens": (
                    delta_response.completion_tokens + header_response.completion_tokens
                ),
            },
        )


def _merge_ledger(delta: StructuredState, previous: CompactionArtifact | None) -> StructuredState:
    if previous is None:
        return delta
    prev = previous.structured_state
    return StructuredState(
        immutable_facts=list(delta.immutable_facts),
        locked_decisions=uniq_preserve_order(
            list(prev.locked_decisions) + list(delta.locked_decisions)
        ),
        deferred_items=uniq_preserve_order(list(prev.deferred_items) + list(delta.deferred_items)),
        forbidden_behaviors=uniq_preserve_order(
            list(prev.forbidden_behaviors) + list(delta.forbidden_behaviors)
        ),
        entity_map={**prev.entity_map, **delta.entity_map},
        unresolved_items=uniq_preserve_order(
            list(prev.unresolved_items) + list(delta.unresolved_items)
        ),
    )


def _cycles_accumulated(previous: CompactionArtifact | None) -> int:
    if previous is None:
        return 1
    prev_count_raw = previous.method_metadata.get("cycles_accumulated", 0)
    prev_count = prev_count_raw if isinstance(prev_count_raw, int) else 0
    return prev_count + 1
