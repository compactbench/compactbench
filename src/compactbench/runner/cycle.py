"""Execute a single drift cycle for one case.

One cycle = extend transcript (cycles >=1) → compact → evaluate → score.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from compactbench.compactors import Compactor
from compactbench.contracts import CompactionArtifact, GeneratedCase, Scorecard, Transcript
from compactbench.providers import Provider
from compactbench.runner.continuation import extend_with_continuation
from compactbench.runner.evaluation import evaluate_items
from compactbench.scoring import score_cycle


@dataclass(frozen=True)
class CycleExecutionResult:
    scorecard: Scorecard
    artifact: CompactionArtifact
    extended_transcript: Transcript
    latency_ms: int


async def execute_cycle(
    *,
    case: GeneratedCase,
    transcript: Transcript,
    cycle_number: int,
    previous_artifact: CompactionArtifact | None,
    compactor: Compactor,
    provider: Provider,
    model: str,
    case_seed: int,
) -> CycleExecutionResult:
    """Compact, evaluate, and score a single cycle.

    For ``cycle_number >= 1`` with a ``previous_artifact``, the transcript is
    first extended with one user/assistant continuation pair so the method
    must survive repeated compact → continue → compact loops.
    """
    started = time.perf_counter()

    working_transcript = transcript
    if cycle_number >= 1 and previous_artifact is not None:
        working_transcript = await extend_with_continuation(
            working_transcript,
            previous_artifact,
            provider,
            model,
            case_seed,
            cycle_number,
        )

    artifact = await compactor.compact(working_transcript, previous_artifact=previous_artifact)
    responses = await evaluate_items(case.evaluation_items, artifact, provider, model)
    scorecard = score_cycle(
        case,
        artifact,
        responses,
        cycle_number=cycle_number,
        source_transcript=working_transcript,
    )

    latency_ms = int((time.perf_counter() - started) * 1000)
    return CycleExecutionResult(
        scorecard=scorecard,
        artifact=artifact,
        extended_transcript=working_transcript,
        latency_ms=latency_ms,
    )
