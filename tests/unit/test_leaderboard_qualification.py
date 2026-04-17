"""Qualification-floor tests."""

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
from compactbench.leaderboard import qualify

pytestmark = pytest.mark.unit


def _scorecard(cycle_number: int = 0, score: float = 0.9) -> Scorecard:
    return Scorecard(
        cycle_number=cycle_number,
        cycle_score=score,
        penalized_cycle_score=score,
        contradiction_rate=0.0,
        compression_ratio=5.0,
        item_scores=[
            ItemScore(
                item_key="q",
                item_type="planning_soundness",
                score=score,
                weight=1.0,
                check_type="contains_normalized",
            ),
        ],
    )


def _case(template_key: str, *, n_cycles: int = 2, case_score: float = 0.9) -> CaseResult:
    return CaseResult(
        case_id=f"{template_key}:s1:dmedium",
        template_key=template_key,
        seed=1,
        cycles=[CycleResult(cycle_number=i, scorecard=_scorecard(i)) for i in range(n_cycles)],
        case_score=case_score,
        drift_resistance=1.0,
    )


def _run(
    *,
    compression: float = 5.0,
    contradiction: float = 0.02,
    overall: float = 0.9,
    cases: list[CaseResult] | None = None,
) -> RunResult:
    effective_cases = cases if cases is not None else [_case("buried_constraint_v1")]
    return RunResult(
        run_id="r-1",
        method_name="m",
        method_version="1.0.0",
        suite_key="elite",
        suite_version="1.0.0",
        scorer_version="1.0.0",
        target_provider="groq",
        target_model="llama-3.3-70b-versatile",
        started_at=datetime(2026, 4, 17, tzinfo=UTC),
        completed_at=datetime(2026, 4, 17, tzinfo=UTC),
        cases=effective_cases,
        overall_score=overall,
        drift_resistance=0.95,
        constraint_retention=0.9,
        contradiction_rate=contradiction,
        compression_ratio=compression,
    )


def test_qualifies_when_all_floors_met() -> None:
    result = qualify(_run(compression=5.0), tier="Elite-Mid", expected_drift_cycles=1)
    assert result.qualified
    assert result.reasons == []


def test_rejected_when_compression_below_tier_floor() -> None:
    result = qualify(_run(compression=3.0), tier="Elite-Mid", expected_drift_cycles=1)
    assert not result.qualified
    assert any("compression" in r for r in result.reasons)


def test_rejected_when_contradiction_rate_above_threshold() -> None:
    result = qualify(
        _run(compression=5.0, contradiction=0.15),
        tier="Elite-Mid",
        expected_drift_cycles=1,
    )
    assert not result.qualified
    assert any("contradiction_rate" in r for r in result.reasons)


def test_rejected_when_no_cases_completed() -> None:
    result = qualify(_run(cases=[]), tier="Elite-Mid", expected_drift_cycles=1)
    assert not result.qualified
    assert any("no cases" in r for r in result.reasons)


def test_rejected_when_case_missing_cycles() -> None:
    short_case = _case("buried_constraint_v1", n_cycles=1)
    result = qualify(
        _run(cases=[short_case]),
        tier="Elite-Mid",
        expected_drift_cycles=2,  # expected 3 cycles (0, 1, 2); case only has 1
    )
    assert not result.qualified
    assert any("cycles" in r for r in result.reasons)


def test_multi_family_requires_each_family_above_min_pass_rate() -> None:
    strong = _case("buried_constraint_v1", case_score=0.9)
    weak = _case("decision_override_v1", case_score=0.2)  # below 0.40 threshold
    result = qualify(
        _run(cases=[strong, weak]),
        tier="Elite-Mid",
        expected_drift_cycles=1,
    )
    assert not result.qualified
    # Family is inferred from template_key: "decision_override_v1" → "decision_override".
    assert any("decision_override" in r for r in result.reasons)


def test_single_family_does_not_trigger_diversity_guard() -> None:
    # Even though the single case has a low score, the diversity guard only
    # applies when there are 2+ families.
    low_case = _case("buried_constraint_v1", case_score=0.2)
    result = qualify(
        _run(cases=[low_case]),
        tier="Elite-Mid",
        expected_drift_cycles=1,
    )
    # Not disqualified by the diversity guard — pass_rate < 0.4 is fine because
    # only one family is present.
    assert all("category-diversity" not in r for r in result.reasons)


def test_multiple_reasons_accumulate() -> None:
    result = qualify(
        _run(compression=1.0, contradiction=0.5, cases=[]),
        tier="Elite-Mid",
        expected_drift_cycles=1,
    )
    assert not result.qualified
    assert len(result.reasons) >= 2  # compression + contradiction + no cases
