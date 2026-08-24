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
from compactbench.runner.persistence import INCOMPLETE_RUN_NOTE

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


def _simple_run(
    *,
    method_name: str = "some-method",
    compression_ratio: float = 6.0,
    contradiction_rate: float = 0.0,
    drift_resistance: float = 0.9,
) -> RunResult:
    return RunResult(
        run_id="r",
        method_name=method_name,
        method_version="1.0.0",
        suite_key="elite_practice",
        suite_version="1.0.0",
        scorer_version="1.0.0",
        target_provider="ollama",
        target_model="m",
        started_at=datetime(2026, 8, 24, tzinfo=UTC),
        completed_at=datetime(2026, 8, 24, tzinfo=UTC),
        cases=[_case("buried_constraint_v1")],
        overall_score=0.6,
        drift_resistance=drift_resistance,
        constraint_retention=0.6,
        contradiction_rate=contradiction_rate,
        compression_ratio=compression_ratio,
    )


class TestDegenerateAndControlRuns:
    """Guards for the ways a non-method used to score well."""

    def test_null_control_cannot_qualify(self) -> None:
        """The arm that returns nothing must never be rankable.

        It reports ~450x compression on the shipped suites, which cleared every
        tier and maxed the compression bonus while retaining no information.
        """
        result = qualify(
            _simple_run(method_name="null", compression_ratio=450.0),
            tier="Elite-Mid",
            expected_drift_cycles=2,
        )
        assert not result.qualified
        assert any("control arm" in r for r in result.reasons)

    def test_oracle_control_cannot_qualify(self) -> None:
        result = qualify(
            _simple_run(method_name="oracle", compression_ratio=1.0),
            tier="Elite-Light",
            expected_drift_cycles=2,
        )
        assert not result.qualified
        assert any("control arm" in r for r in result.reasons)

    def test_implausible_compression_is_rejected_even_for_a_named_method(self) -> None:
        """A submitted method returning an empty artifact is caught on the number.

        Renaming the null strategy is not a way around the control check.
        """
        result = qualify(
            _simple_run(method_name="totally-legit-method", compression_ratio=450.0),
            tier="Elite-Mid",
            expected_drift_cycles=2,
        )
        assert not result.qualified
        assert any("plausible maximum" in r for r in result.reasons)

    def test_zero_drift_cycles_cannot_qualify(self) -> None:
        """`--drift-cycles 0` was the cheapest route to 30% of elite_score."""
        result = qualify(_simple_run(), tier="Elite-Mid", expected_drift_cycles=0)
        assert not result.qualified
        assert any("drift resistance is measurable" in r for r in result.reasons)

    def test_a_normal_run_still_qualifies(self) -> None:
        """The new floors must not reject legitimate submissions."""
        # 1 drift cycle = 2 total cycles, the minimum at which drift is
        # measurable, and what the shared `_case` helper builds.
        result = qualify(_simple_run(), tier="Elite-Mid", expected_drift_cycles=1)
        assert result.qualified, result.reasons


def test_incomplete_run_cannot_qualify() -> None:
    """A crashed or in-flight run must not be rankable.

    `read_run_result` reconstructs aggregates from whichever cases landed when
    there is no `run_end` event. Ranking that publishes an unrepresentative
    number, and makes "kill the run once the easy cases are through" a cheap
    way to cherry-pick a score.
    """
    run = _simple_run().model_copy(update={"notes": [INCOMPLETE_RUN_NOTE]})
    result = qualify(run, tier="Elite-Mid", expected_drift_cycles=1)
    assert not result.qualified
    assert any("incomplete" in r for r in result.reasons)


def test_complete_run_with_other_notes_still_qualifies() -> None:
    """Only the incomplete marker disqualifies — notes are otherwise free-form."""
    run = _simple_run().model_copy(update={"notes": ["ran on a rainy Tuesday"]})
    assert qualify(run, tier="Elite-Mid", expected_drift_cycles=1).qualified
