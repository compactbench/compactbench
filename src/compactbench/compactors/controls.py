"""Control arms: the reference points every real score is read against.

A compaction score in isolation says nothing. "hybrid-ledger scored 0.61" is
uninterpretable without knowing what a method that keeps *everything* scores on
the same cases (some items are simply hard for the reader), and what a method
that keeps *nothing* scores (some items are answerable by guessing). Those two
numbers bracket the achievable range; a real method's position inside that
bracket is the actual result.

None of these makes a model call — they are deterministic, free, and fast:

``oracle``
    Carries the whole conversation forward verbatim: its previous artifact plus
    the new turns. Upper bound: the score when compaction loses nothing. It
    ignores the token budget by design and is never ranked.

``null``
    Returns an empty artifact. Lower bound: the score obtainable with no
    information at all.

``truncate-last-n``
    Keeps the most recent turns verbatim and drops the rest: as many as fit the
    token budget (or the last 10 when there is no budget). What most production
    systems did before they had a compaction layer; a method that cannot beat
    it is not earning its model calls.
"""

from __future__ import annotations

from typing import ClassVar, cast

from compactbench.compactors._utils import fit_summary_text
from compactbench.compactors.base import Compactor
from compactbench.contracts import CompactionArtifact, CompactionRequest
from compactbench.rendering import render_turn
from compactbench.tokens import count_tokens


class OracleCompactor(Compactor):
    """Upper-bound control: the conversation, uncompacted."""

    name: ClassVar[str] = "oracle"
    version: ClassVar[str] = "2.0.0"

    async def compact(self, request: CompactionRequest) -> CompactionArtifact:
        parts: list[str] = []
        if request.previous_artifact is not None and request.previous_artifact.summary_text:
            parts.append(request.previous_artifact.summary_text)
        parts.extend(render_turn(t) for t in request.turns)
        text, warnings = fit_summary_text("\n\n".join(parts))
        return CompactionArtifact(
            summaryText=text,
            selectedSourceTurnIds=[t.id for t in request.turns],
            warnings=warnings,
            methodMetadata={"control": "oracle"},
        )


class NullCompactor(Compactor):
    """Lower-bound control: returns nothing at all."""

    name: ClassVar[str] = "null"
    version: ClassVar[str] = "2.0.0"

    async def compact(self, request: CompactionRequest) -> CompactionArtifact:
        return CompactionArtifact(methodMetadata={"control": "null"})


class TruncateLastNCompactor(Compactor):
    """Naive control: keep the newest turns verbatim, discard everything earlier.

    Strong on anything stated recently and blind to anything stated early —
    exactly the failure mode the ``buried_constraint`` family probes.
    """

    name: ClassVar[str] = "truncate-last-n"
    version: ClassVar[str] = "2.0.0"

    #: Turns kept when the run sets no token budget.
    n: ClassVar[int] = 10
    # Room for the "SUMMARY:" label and blank lines the renderer adds.
    _OVERHEAD: ClassVar[int] = 8

    async def compact(self, request: CompactionRequest) -> CompactionArtifact:
        previous: list[str] = []
        if request.previous_artifact is not None:
            raw = request.previous_artifact.method_metadata.get("kept_turns", [])
            if isinstance(raw, list):
                previous = [s for s in cast("list[object]", raw) if isinstance(s, str)]
        candidates = previous + [render_turn(t) for t in request.turns]

        kept: list[str] = []
        if request.token_budget is None:
            kept = candidates[-self.n :]
        else:
            used = self._OVERHEAD
            for turn in reversed(candidates):
                cost = count_tokens(turn) + 2
                if used + cost > request.token_budget:
                    break
                kept.insert(0, turn)
                used += cost

        text, warnings = fit_summary_text("\n\n".join(kept))
        return CompactionArtifact(
            summaryText=text,
            selectedSourceTurnIds=[t.id for t in request.turns],
            warnings=warnings,
            methodMetadata={"control": "truncate-last-n", "kept_turns": kept},
        )
