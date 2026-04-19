"""Per-item-type diagnostic breakdown across a completed run.

This module rolls the per-cycle ``ItemScore`` records up to a per-item-type
view. It answers the question: *which kinds of evaluation items is this
compaction method losing points on?* — a view that is otherwise buried in the
scorecard details.

Ordering convention: worst mean score first (descending pain), then heaviest
weight first (breaks ties toward the most impactful), then item_type
alphabetically (deterministic tail).
"""

from __future__ import annotations

from collections import defaultdict

from pydantic import BaseModel, ConfigDict, Field

from compactbench.contracts import ItemScore, RunResult


class ItemTypeBreakdown(BaseModel):
    """Rolled-up scoring stats for one item_type across a run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    item_type: str
    total: int = Field(ge=0)
    mean_score: float = Field(ge=0.0, le=1.0)
    perfect: int = Field(ge=0)
    partial: int = Field(ge=0)
    failed: int = Field(ge=0)
    weight: float = Field(gt=0.0)


def _bucket(score: float) -> str:
    if score >= 1.0:
        return "perfect"
    if score <= 0.0:
        return "failed"
    return "partial"


def item_type_breakdown(run_result: RunResult) -> list[ItemTypeBreakdown]:
    """Group every ItemScore in ``run_result`` by item_type and summarize.

    Walks every cycle of every case. Each item_type's breakdown reports the
    total count, how many were perfect / partial / catastrophic, the mean
    score, and the per-item weight (which is constant per type by construction
    in :mod:`compactbench.scoring.scorer`).

    Returns ``[]`` when the run recorded no item scores. Ordering puts the
    worst performers first so CLI readers see the problem areas without
    scrolling.
    """
    groups: dict[str, list[ItemScore]] = defaultdict(list)
    for case in run_result.cases:
        for cycle in case.cycles:
            for score in cycle.scorecard.item_scores:
                groups[score.item_type].append(score)

    breakdowns: list[ItemTypeBreakdown] = []
    for item_type, scores in groups.items():
        total = len(scores)
        if total == 0:
            continue
        mean = sum(s.score for s in scores) / total
        buckets: dict[str, int] = {"perfect": 0, "partial": 0, "failed": 0}
        for s in scores:
            buckets[_bucket(s.score)] += 1
        weight = scores[0].weight
        breakdowns.append(
            ItemTypeBreakdown(
                item_type=item_type,
                total=total,
                mean_score=mean,
                perfect=buckets["perfect"],
                partial=buckets["partial"],
                failed=buckets["failed"],
                weight=weight,
            )
        )

    breakdowns.sort(key=lambda b: (b.mean_score, -b.weight, b.item_type))
    return breakdowns
