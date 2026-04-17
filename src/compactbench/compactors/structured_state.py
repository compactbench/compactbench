"""Structured-state baseline: JSON-only extraction, no prose."""

from __future__ import annotations

from typing import Any, ClassVar

from compactbench.compactors._state_parser import parse_state
from compactbench.compactors._utils import render_transcript
from compactbench.compactors.base import Compactor
from compactbench.contracts import CompactionArtifact, Transcript
from compactbench.providers import CompletionRequest

_PROMPT = (
    "Extract a strict JSON object summarizing the current state of this "
    "conversation. Return ONLY the JSON, no prose or markdown fencing.\n\n"
    "Required fields (all must be present; use empty arrays or an empty object "
    "when none apply):\n"
    "- immutable_facts: array of strings — facts that must not change\n"
    "- locked_decisions: array of strings — decisions the user committed to\n"
    "- deferred_items: array of strings — items explicitly postponed\n"
    "- forbidden_behaviors: array of strings — things the assistant must never do\n"
    "- entity_map: object mapping entity names to a role label\n"
    "- unresolved_items: array of strings — open tasks or questions\n\n"
    "CONVERSATION:\n{transcript}\n\n"
    "JSON:"
)


class StructuredStateCompactor(Compactor):
    """JSON-forced structured extraction; no ``summaryText``."""

    name: ClassVar[str] = "structured-state"
    version: ClassVar[str] = "1.0.0"

    async def compact(
        self,
        transcript: Transcript,
        config: dict[str, Any] | None = None,
        previous_artifact: CompactionArtifact | None = None,
    ) -> CompactionArtifact:
        prompt = _PROMPT.format(transcript=render_transcript(transcript))
        response = await self.provider.complete(
            CompletionRequest(
                model=self.model,
                prompt=prompt,
                response_format={"type": "json_object"},
            )
        )
        state, warnings = parse_state(response.text)
        return CompactionArtifact(
            summaryText="",
            structured_state=state,
            selectedSourceTurnIds=[t.id for t in transcript.turns],
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
