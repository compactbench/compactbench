"""Orchestrate per-cycle scoring: checks → weighted aggregate → penalty → scorecard.

Weights are locked in docs/architecture/decisions.md §B3. Changing them is a
scorer-version bump.
"""

from __future__ import annotations

from compactbench.contracts import (
    CompactionArtifact,
    EvaluationItem,
    EvaluationItemType,
    GeneratedCase,
    ItemScore,
    Scorecard,
)
from compactbench.scoring.checks import run_check
from compactbench.scoring.compression import compression_ratio
from compactbench.scoring.contradictions import contradiction_rate

WEIGHTS: dict[EvaluationItemType, float] = {
    EvaluationItemType.LOCKED_DECISION_RETENTION: 3.0,
    EvaluationItemType.FORBIDDEN_BEHAVIOR_RETENTION: 3.0,
    EvaluationItemType.IMMUTABLE_FACT_RECALL: 2.0,
    EvaluationItemType.UNRESOLVED_TASK_CONTINUITY: 2.0,
    EvaluationItemType.ENTITY_INTEGRITY: 1.0,
    EvaluationItemType.PLANNING_SOUNDNESS: 1.0,
}


def score_item(item: EvaluationItem, response: str) -> ItemScore:
    """Score a single evaluation item against a response."""
    check_type = str(item.expected.get("check", "unknown"))
    raw = run_check(item.expected, response)
    return ItemScore(
        item_key=item.key,
        item_type=item.item_type.value,
        score=raw,
        weight=WEIGHTS.get(item.item_type, 1.0),
        check_type=check_type,
        details={},
    )


def _weighted_cycle_score(item_scores: list[ItemScore]) -> float:
    if not item_scores:
        return 0.0
    total_weight = sum(i.weight for i in item_scores)
    if total_weight <= 0:
        return 0.0
    return sum(i.score * i.weight for i in item_scores) / total_weight


def score_cycle(
    case: GeneratedCase,
    artifact: CompactionArtifact,
    responses: dict[str, str],
    cycle_number: int = 0,
) -> Scorecard:
    """Score one cycle of a compaction run and return a :class:`Scorecard`."""
    if cycle_number < 0:
        raise ValueError(f"cycle_number must be >= 0, got {cycle_number}")

    item_scores = [score_item(item, responses.get(item.key, "")) for item in case.evaluation_items]
    cycle_score = _weighted_cycle_score(item_scores)
    contra = contradiction_rate(case.evaluation_items, responses, case.ground_truth)
    penalized = max(0.0, min(1.0, cycle_score * (1.0 - contra)))
    comp_ratio = compression_ratio(case.transcript, artifact)

    return Scorecard(
        cycle_number=cycle_number,
        cycle_score=cycle_score,
        penalized_cycle_score=penalized,
        contradiction_rate=contra,
        compression_ratio=comp_ratio,
        item_scores=item_scores,
    )
