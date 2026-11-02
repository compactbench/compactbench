"""Structured-state baseline: JSON-only extraction, no prose."""

from __future__ import annotations

from typing import ClassVar

from compactbench.compactors._state_parser import parse_state
from compactbench.compactors._utils import (
    budget_instruction,
    finalize,
    output_tokens,
    reasoning_effort,
)
from compactbench.compactors.base import Compactor
from compactbench.contracts import CompactionArtifact, CompactionRequest
from compactbench.providers import CompletionRequest
from compactbench.rendering import render_request

_PROMPT = (
    "Maintain a strict JSON object describing the current state of a long-running "
    "conversation. The text below will be replaced by your JSON, so anything you "
    "leave out is lost. When a newer turn changes or revokes something, keep only "
    "the current version. Return ONLY the JSON, no prose or markdown fencing.\n\n"
    "Required fields (all must be present; use empty arrays or an empty object "
    "when none apply):\n"
    "- immutable_facts: array of strings — facts, numbers, dates and identifiers\n"
    "- locked_decisions: array of strings — current decisions and what they replaced\n"
    "- deferred_items: array of strings — items explicitly postponed\n"
    "- forbidden_behaviors: array of strings — rules that currently apply, with their scope\n"
    "- entity_map: object mapping each person or thing to their current role\n"
    "- unresolved_items: array of strings — open tasks and questions, with owners\n\n"
    "{length}\n\n"
    "{body}\n\n"
    "JSON:"
)


class StructuredStateCompactor(Compactor):
    """JSON-forced structured extraction; no ``summaryText``."""

    name: ClassVar[str] = "structured-state"
    version: ClassVar[str] = "2.0.0"

    async def compact(self, request: CompactionRequest) -> CompactionArtifact:
        prompt = _PROMPT.format(body=render_request(request), length=budget_instruction(request))
        response = await self.provider.complete(
            CompletionRequest(
                model=self.model,
                prompt=prompt,
                response_format={"type": "json_object"},
                max_tokens=output_tokens(request),
                reasoning_effort=reasoning_effort(self.config),
            )
        )
        state, warnings = parse_state(response.text)
        artifact = CompactionArtifact(
            summaryText="",
            structured_state=state,
            selectedSourceTurnIds=[t.id for t in request.turns],
            warnings=warnings,
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
