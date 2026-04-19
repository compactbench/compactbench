"""Execute a single drift cycle for one case.

One cycle = extend transcript (cycles >=1) → compact → evaluate → score.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from compactbench.compactors import Compactor
from compactbench.contracts import (
    CompactionArtifact,
    GeneratedCase,
    Scorecard,
    TokenUsage,
    Transcript,
)
from compactbench.providers import CountingProvider, Provider
from compactbench.runner.continuation import extend_with_continuation
from compactbench.runner.evaluation import evaluate_items
from compactbench.scoring import score_cycle


@dataclass(frozen=True)
class CycleExecutionResult:
    scorecard: Scorecard
    artifact: CompactionArtifact
    extended_transcript: Transcript
    latency_ms: int
    # ``None`` when the runner did not wrap the provider in a
    # :class:`CountingProvider`. Older callers that pass a raw provider get
    # the legacy no-telemetry shape; the runner always wraps.
    token_usage: TokenUsage | None = None


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

    When ``provider`` is a :class:`CountingProvider`, the wrapper's accumulator
    is reset at entry and snapshotted on exit so the returned
    :class:`CycleExecutionResult` carries precise per-cycle token counts. The
    reset is a necessary side-effect of measuring "just this cycle" when cases
    run under concurrency — a single global accumulator cannot attribute calls
    to the cycle that made them, so the runner hands each case its own
    ``CountingProvider`` and this function drains it between cycles.
    """
    started = time.perf_counter()

    counting = provider if isinstance(provider, CountingProvider) else None
    if counting is not None:
        await counting.reset()

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
    token_usage = await counting.snapshot() if counting is not None else None
    return CycleExecutionResult(
        scorecard=scorecard,
        artifact=artifact,
        extended_transcript=working_transcript,
        latency_ms=latency_ms,
        token_usage=token_usage,
    )
