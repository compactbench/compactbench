"""Control arms: the reference points every real score is read against.

A compaction score in isolation says nothing. "hybrid-ledger scored 0.61" is
uninterpretable without knowing what a method that keeps *everything* scores on
the same cases (some items are simply hard, or the grader is strict), and what a
method that keeps *nothing* scores (some items are answerable by guessing, or
are free points). Those two numbers bracket the achievable range; a real method's
position inside that bracket is the actual result.

Three arms live here, none of which makes a model call — they are deterministic,
free, and fast, so there is no reason not to run them alongside every experiment:

``oracle``
    Returns the transcript verbatim. Upper bound: the score when compaction
    loses nothing. If a real method matches the oracle, it lost nothing that
    the evaluation items ask about.

``null``
    Returns an empty artifact. Lower bound: the score obtainable with no
    information at all. Any item the null arm passes is a free point and is
    measuring the grader rather than the method — a diagnostic the suite badly
    needs, since roughly a third of shipped items are ``forbidden_absent``
    checks that an empty answer satisfies by construction.

``truncate-last-n``
    Keeps the last N turns verbatim and drops the rest. The dumbest thing that
    could possibly work, and what most production systems actually did before
    they had a compaction layer. A method that cannot beat this is not earning
    its model calls.
"""

from __future__ import annotations

from typing import Any, ClassVar

from compactbench.compactors.base import Compactor
from compactbench.contracts import CompactionArtifact, Transcript
from compactbench.providers import Provider

# CompactionArtifact caps summary_text at 8000 characters. That is a sensible
# ceiling for a *compaction* artifact but it also bounds how much context the
# oracle can carry, so the oracle records a warning when it has to cut. At
# current suite sizes (elite transcripts run ~2k characters) nothing is cut.
_SUMMARY_TEXT_LIMIT = 8000


def _render_turns(transcript: Transcript) -> str:
    return "\n".join(f"{turn.role.value}: {turn.content}" for turn in transcript.turns)


def _fit(text: str) -> tuple[str, list[str]]:
    """Trim ``text`` to the artifact's summary cap, reporting whether it cut."""
    if len(text) <= _SUMMARY_TEXT_LIMIT:
        return text, []
    return text[:_SUMMARY_TEXT_LIMIT], [
        f"transcript exceeded the {_SUMMARY_TEXT_LIMIT}-character artifact summary cap "
        f"and was truncated: this control is no longer a true upper bound for this case"
    ]


class OracleCompactor(Compactor):
    """Upper-bound control: hands the model the full transcript, uncompacted.

    Not a compaction method — it is the "compaction lost nothing" reference.
    Its compression ratio is ~1.0 by construction, so it will never qualify for
    the leaderboard, which is correct: it exists to bound the score, not to
    compete.
    """

    name: ClassVar[str] = "oracle"
    version: ClassVar[str] = "1.0.0"

    def __init__(self, provider: Provider, model: str) -> None:
        super().__init__(provider, model)

    async def compact(
        self,
        transcript: Transcript,
        config: dict[str, Any] | None = None,
        previous_artifact: CompactionArtifact | None = None,
    ) -> CompactionArtifact:
        text, warnings = _fit(_render_turns(transcript))
        return CompactionArtifact(
            summaryText=text,
            selectedSourceTurnIds=[t.id for t in transcript.turns],
            warnings=warnings,
            methodMetadata={"control": "oracle"},
        )


class NullCompactor(Compactor):
    """Lower-bound control: returns nothing at all.

    Every point this arm scores is a point available without information.
    Reading a real method's score without subtracting this floor overstates it.
    """

    name: ClassVar[str] = "null"
    version: ClassVar[str] = "1.0.0"

    def __init__(self, provider: Provider, model: str) -> None:
        super().__init__(provider, model)

    async def compact(
        self,
        transcript: Transcript,
        config: dict[str, Any] | None = None,
        previous_artifact: CompactionArtifact | None = None,
    ) -> CompactionArtifact:
        return CompactionArtifact(methodMetadata={"control": "null"})


class TruncateLastNCompactor(Compactor):
    """Naive control: keep the last ``n`` turns verbatim, discard everything earlier.

    The baseline a real method has to beat to justify its cost. It is strong on
    anything stated recently and blind to anything stated early, which is
    precisely the failure mode the ``buried_constraint`` family probes.
    """

    name: ClassVar[str] = "truncate-last-n"
    version: ClassVar[str] = "1.0.0"

    #: Turns retained. 10 keeps the control meaningfully lossy at every shipped
    #: difficulty (elite cases run 36 turns) without being degenerate at easy.
    n: ClassVar[int] = 10

    def __init__(self, provider: Provider, model: str) -> None:
        super().__init__(provider, model)

    async def compact(
        self,
        transcript: Transcript,
        config: dict[str, Any] | None = None,
        previous_artifact: CompactionArtifact | None = None,
    ) -> CompactionArtifact:
        kept = transcript.turns[-self.n :]
        text, warnings = _fit(_render_turns(Transcript(turns=list(kept))))
        return CompactionArtifact(
            summaryText=text,
            selectedSourceTurnIds=[t.id for t in kept],
            warnings=warnings,
            methodMetadata={"control": "truncate-last-n", "n": self.n},
        )
