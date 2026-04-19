"""Tests for per-item-type diagnostic breakdown."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from compactbench.contracts import (
    CaseResult,
    CycleResult,
    ItemScore,
    RunResult,
    Scorecard,
)
from compactbench.scoring import ItemTypeBreakdown, item_type_breakdown

pytestmark = pytest.mark.unit


def _item_score(key: str, item_type: str, score: float, weight: float = 1.0) -> ItemScore:
    return ItemScore(
        item_key=key,
        item_type=item_type,
        score=score,
        weight=weight,
        check_type="contains_normalized",
    )


def _cycle(cycle: int, item_scores: list[ItemScore]) -> CycleResult:
    return CycleResult(
        cycle_number=cycle,
        scorecard=Scorecard(
            cycle_number=cycle,
            cycle_score=0.0,
            penalized_cycle_score=0.0,
            contradiction_rate=0.0,
            compression_ratio=1.0,
            item_scores=item_scores,
        ),
    )


def _case(case_id: str, cycles: list[CycleResult]) -> CaseResult:
    return CaseResult(
        case_id=case_id,
        template_key="t",
        seed=1,
        cycles=cycles,
        case_score=0.0,
        drift_resistance=1.0,
    )


def _run(cases: list[CaseResult]) -> RunResult:
    now = datetime.now(tz=UTC)
    return RunResult(
        run_id="r",
        method_name="m",
        method_version="v",
        suite_key="s",
        suite_version="sv",
        scorer_version="1.0.0",
        target_provider="mock",
        target_model="mock",
        started_at=now,
        completed_at=now,
        cases=cases,
        overall_score=0.0,
        drift_resistance=1.0,
        constraint_retention=1.0,
        contradiction_rate=0.0,
        compression_ratio=1.0,
    )


def test_empty_run_returns_empty_breakdown() -> None:
    assert item_type_breakdown(_run([])) == []


def test_buckets_perfect_partial_failed() -> None:
    run = _run(
        [
            _case(
                "c1",
                [
                    _cycle(
                        0,
                        [
                            _item_score("a", "entity_integrity", 1.0),
                            _item_score("b", "entity_integrity", 0.0),
                            _item_score("c", "entity_integrity", 0.5),
                        ],
                    )
                ],
            )
        ]
    )
    [row] = item_type_breakdown(run)
    assert row.item_type == "entity_integrity"
    assert row.total == 3
    assert row.perfect == 1
    assert row.partial == 1
    assert row.failed == 1
    assert row.mean_score == pytest.approx(0.5)


def test_breakdown_aggregates_across_cases_and_cycles() -> None:
    run = _run(
        [
            _case(
                "c1",
                [
                    _cycle(0, [_item_score("a", "entity_integrity", 1.0)]),
                    _cycle(1, [_item_score("a", "entity_integrity", 0.0)]),
                ],
            ),
            _case(
                "c2",
                [_cycle(0, [_item_score("b", "entity_integrity", 1.0)])],
            ),
        ]
    )
    [row] = item_type_breakdown(run)
    assert row.total == 3
    assert row.perfect == 2
    assert row.failed == 1
    assert row.mean_score == pytest.approx(2 / 3)


def test_ordering_puts_worst_mean_first() -> None:
    run = _run(
        [
            _case(
                "c1",
                [
                    _cycle(
                        0,
                        [
                            _item_score("a", "type_good", 1.0),
                            _item_score("b", "type_bad", 0.0),
                            _item_score("c", "type_mid", 0.5),
                        ],
                    )
                ],
            )
        ]
    )
    ordered = [row.item_type for row in item_type_breakdown(run)]
    assert ordered == ["type_bad", "type_mid", "type_good"]


def test_tie_breaks_by_weight_desc_then_item_type_asc() -> None:
    run = _run(
        [
            _case(
                "c1",
                [
                    _cycle(
                        0,
                        [
                            _item_score("a", "alpha", 1.0, weight=1.0),
                            _item_score("b", "bravo", 1.0, weight=3.0),
                            _item_score("c", "charlie", 1.0, weight=2.0),
                        ],
                    )
                ],
            )
        ]
    )
    ordered = [row.item_type for row in item_type_breakdown(run)]
    assert ordered == ["bravo", "charlie", "alpha"]


def test_breakdown_preserves_per_type_weight() -> None:
    run = _run(
        [
            _case(
                "c1",
                [
                    _cycle(
                        0,
                        [
                            _item_score("a", "locked_decision_retention", 1.0, weight=3.0),
                            _item_score("b", "entity_integrity", 1.0, weight=1.0),
                        ],
                    )
                ],
            )
        ]
    )
    by_type = {row.item_type: row for row in item_type_breakdown(run)}
    assert by_type["locked_decision_retention"].weight == pytest.approx(3.0)
    assert by_type["entity_integrity"].weight == pytest.approx(1.0)


def test_breakdown_is_pydantic_frozen() -> None:
    from pydantic import ValidationError

    row = ItemTypeBreakdown(
        item_type="entity_integrity",
        total=1,
        mean_score=1.0,
        perfect=1,
        partial=0,
        failed=0,
        weight=1.0,
    )
    with pytest.raises(ValidationError, match="frozen"):
        row.item_type = "other"  # type: ignore[misc]
