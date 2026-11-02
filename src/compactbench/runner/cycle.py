"""Execute one compaction cycle of one case.

One cycle = compact (previous artifact + new turns) → enforce the token budget
→ the reader answers the cycle's probes from the artifact → score. With
controls on, the same probes are also answered from the full conversation
(oracle) and from nothing (null), on the same cases, so the run carries its
own ceiling and floor.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from statistics import fmean

from compactbench.compactors import Compactor
from compactbench.contracts import (
    CompactionArtifact,
    CompactionRequest,
    CycleResult,
    GeneratedCase,
    Probe,
)
from compactbench.providers import CountingProvider, ReasoningEffort
from compactbench.rendering import render_artifact, render_request, render_turns
from compactbench.runner.reader import DEFAULT_CHUNK_SIZE, read
from compactbench.scoring.answers import counted, score_probe
from compactbench.tokens import count_tokens, head_tokens


@dataclass(frozen=True)
class CycleExecution:
    result: CycleResult
    artifact: CompactionArtifact
    visible_context: str
    answers: dict[str, object]
    reader_responses: list[str]
    turn_ids: list[int]


async def _control_scores(
    reader: CountingProvider,
    model: str,
    context: str,
    probes: list[Probe],
    chunk_size: int,
    effort: ReasoningEffort | None,
) -> list[float]:
    """Per-probe scores when the same probes are answered from ``context``."""
    outcome = await read(reader, model, context, probes, chunk_size=chunk_size, effort=effort)
    return [score_probe(p, outcome.answers.get(p.key)).score for p in probes]


async def execute_cycle(
    *,
    case: GeneratedCase,
    cycle: int,
    previous_artifact: CompactionArtifact | None,
    compactor: Compactor,
    compactor_provider: CountingProvider,
    reader: CountingProvider,
    reader_model: str,
    budget_tokens: int | None,
    controls: bool = False,
    control_reader: CountingProvider | None = None,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    reader_effort: ReasoningEffort | None = None,
) -> CycleExecution:
    """Run cycle ``cycle`` of ``case``.

    ``budget_tokens`` is ``None`` for methods exempt from the budget (the oracle
    control). Turn ``tags`` are generation metadata that would label the
    answer-bearing turns, so they are stripped before the method sees anything.
    """
    spec = case.cycles[cycle]
    turns = [t.model_copy(update={"tags": []}) for t in spec.turns]
    request = CompactionRequest(
        cycle=cycle,
        turns=turns,
        previous_artifact=previous_artifact,
        token_budget=budget_tokens,
    )

    await compactor_provider.reset()
    started = time.perf_counter()
    artifact = await compactor.compact(request)
    latency_ms = int((time.perf_counter() - started) * 1000)
    compactor_usage = await compactor_provider.snapshot()

    rendered = render_artifact(artifact)
    artifact_tokens = count_tokens(rendered)
    over_budget = budget_tokens is not None and artifact_tokens > budget_tokens
    visible = head_tokens(rendered, budget_tokens) if over_budget and budget_tokens else rendered

    await reader.reset()
    outcome = await read(
        reader, reader_model, visible, spec.probes, chunk_size=chunk_size, effort=reader_effort
    )
    reader_usage = await reader.snapshot()
    probe_results = [score_probe(p, outcome.answers.get(p.key)) for p in spec.probes]

    oracle_score: float | None = None
    null_score: float | None = None
    control_usage = None
    if controls:
        control = control_reader or reader
        await control.reset()
        full = render_turns(case.transcript_through(cycle).turns)
        oracle = await _control_scores(
            control, reader_model, full, spec.probes, chunk_size, reader_effort
        )
        null = await _control_scores(
            control, reader_model, "", spec.probes, chunk_size, reader_effort
        )
        control_usage = await control.snapshot()
        # Kept per probe so any grouping (a family inside a mixed case) has its own controls.
        probe_results = [
            r.model_copy(update={"oracle_score": o, "null_score": n})
            for r, o, n in zip(probe_results, oracle, null, strict=True)
        ]
        oracle_scored = counted(probe_results, "oracle_score")
        null_scored = counted(probe_results, "null_score")
        oracle_score = fmean(oracle_scored) if oracle_scored else 0.0
        null_score = fmean(null_scored) if null_scored else 0.0

    source_tokens = count_tokens(render_turns(case.transcript_through(cycle).turns))
    result = CycleResult(
        cycle=cycle,
        score=fmean(scored) if (scored := counted(probe_results)) else 0.0,
        probe_results=probe_results,
        source_tokens=source_tokens,
        input_tokens=count_tokens(render_request(request)),
        artifact_tokens=artifact_tokens,
        budget_tokens=budget_tokens,
        over_budget=over_budget,
        latency_ms=latency_ms,
        compactor_usage=compactor_usage,
        reader_usage=reader_usage,
        control_usage=control_usage,
        oracle_score=oracle_score,
        null_score=null_score,
        warnings=list(artifact.warnings),
    )
    return CycleExecution(
        result=result,
        artifact=artifact,
        visible_context=visible,
        answers=dict(outcome.answers),
        reader_responses=outcome.responses,
        turn_ids=[t.id for t in turns],
    )
