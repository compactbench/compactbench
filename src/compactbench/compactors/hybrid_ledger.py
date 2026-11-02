"""Hybrid ledger: append-only structured state across cycles + short prose header."""

from __future__ import annotations

from typing import ClassVar

from compactbench.compactors._state_parser import parse_state
from compactbench.compactors._utils import (
    finalize,
    fit_summary_text,
    output_tokens,
    reasoning_effort,
    uniq_preserve_order,
)
from compactbench.compactors.base import Compactor
from compactbench.contracts import CompactionArtifact, CompactionRequest, StructuredState
from compactbench.providers import CompletionRequest
from compactbench.rendering import render_turns

_DELTA_PROMPT = (
    "Extract NEW state that appears in this conversation segment as a strict "
    "JSON object. Include only items stated or decided in these turns; do not "
    "infer beyond the text. Return ONLY the JSON, no prose.\n\n"
    "Required fields: immutable_facts, locked_decisions, deferred_items, "
    "forbidden_behaviors, entity_map, unresolved_items.\n\n"
    "CONVERSATION SEGMENT:\n{turns}\n\n"
    "JSON:"
)

_HEADER_PROMPT = (
    "Write a 2-to-3 sentence header describing the current situation. "
    "Do not restate constraints or decisions (they are tracked separately). "
    "Focus on: what is being worked on, who is involved, what phase we are in.\n\n"
    "PREVIOUS HEADER:\n{previous}\n\n"
    "NEW TURNS:\n{turns}\n\n"
    "HEADER:"
)


class HybridLedgerCompactor(Compactor):
    """Append-only ledger compactor.

    - ``locked_decisions``, ``forbidden_behaviors``, ``deferred_items``,
      ``unresolved_items`` accumulate across cycles (de-duplicated). Nothing is
      ever removed, so superseded decisions stay in the ledger next to their
      replacements — a known weakness the decision-override family exposes.
    - ``immutable_facts`` accumulate; ``entity_map`` entries are overwritten by
      newer ones with the same key.
    - ``summaryText`` is a short (2-3 sentence) situational header.
    """

    name: ClassVar[str] = "hybrid-ledger"
    version: ClassVar[str] = "2.0.0"

    async def compact(self, request: CompactionRequest) -> CompactionArtifact:
        turns_text = render_turns(request.turns) if request.turns else "(no new turns)"
        delta_response = await self.provider.complete(
            CompletionRequest(
                model=self.model,
                prompt=_DELTA_PROMPT.format(turns=turns_text),
                response_format={"type": "json_object"},
                max_tokens=output_tokens(request),
                reasoning_effort=reasoning_effort(self.config),
            )
        )
        delta, warnings = parse_state(delta_response.text)

        previous_header = (
            request.previous_artifact.summary_text.strip() if request.previous_artifact else ""
        )
        header_response = await self.provider.complete(
            CompletionRequest(
                model=self.model,
                prompt=_HEADER_PROMPT.format(
                    previous=previous_header or "(none)", turns=turns_text
                ),
                max_tokens=output_tokens(request),
                reasoning_effort=reasoning_effort(self.config),
            )
        )

        previous_state = (
            request.previous_artifact.structured_state if request.previous_artifact else None
        )
        header, length_warnings = fit_summary_text(header_response.text.strip())
        artifact = CompactionArtifact(
            summaryText=header,
            structured_state=_merge_ledger(delta, previous_state),
            selectedSourceTurnIds=[t.id for t in request.turns],
            warnings=[*warnings, *length_warnings],
            methodMetadata={
                "method": self.name,
                "version": self.version,
                "model": self.model,
                "provider": self.provider.key,
                "calls": 2,
                "cycles_accumulated": request.cycle + 1,
                "prompt_tokens": delta_response.prompt_tokens + header_response.prompt_tokens,
                "completion_tokens": (
                    delta_response.completion_tokens + header_response.completion_tokens
                ),
            },
        )
        return finalize(artifact, request)


def _merge_ledger(delta: StructuredState, previous: StructuredState | None) -> StructuredState:
    if previous is None:
        return delta

    def _append(old: list[str], new: list[str]) -> list[str]:
        return uniq_preserve_order(list(old) + list(new))[:200]

    return StructuredState(
        immutable_facts=_append(previous.immutable_facts, delta.immutable_facts),
        locked_decisions=_append(previous.locked_decisions, delta.locked_decisions),
        deferred_items=_append(previous.deferred_items, delta.deferred_items),
        forbidden_behaviors=_append(previous.forbidden_behaviors, delta.forbidden_behaviors),
        entity_map={**previous.entity_map, **delta.entity_map},
        unresolved_items=_append(previous.unresolved_items, delta.unresolved_items),
    )
