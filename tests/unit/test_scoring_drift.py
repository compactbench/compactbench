"""Drift-metric tests.

Drift resistance carries 30% of ``elite_score``, so its degenerate cases matter
as much as its normal ones. Several tests here exist specifically to pin
behaviour that the previous additive definition got backwards.
"""

from __future__ import annotations

import pytest

from compactbench.scoring import drift_deltas, drift_resistance
from compactbench.scoring.drift import MIN_CYCLES_FOR_DRIFT, is_measurable

pytestmark = pytest.mark.unit


def test_single_cycle_has_no_deltas() -> None:
    assert drift_deltas([0.9]) == []


def test_deltas_are_relative_to_cycle_zero() -> None:
    assert drift_deltas([1.0, 0.8, 0.6]) == pytest.approx([-0.2, -0.4])


class TestDegenerateInputs:
    """The cases the old additive definition rewarded instead of rejecting."""

    def test_consistent_total_failure_is_not_perfect_resistance(self) -> None:
        """A method that scores zero every cycle has retained nothing.

        Regression: ``clamp(1 + mean(delta))`` returned **1.0** here, because
        the deltas are all zero — perfectly "stable" failure. That handed the
        single worst possible method full marks on the benchmark's headline
        metric and 30% of the ranking weight.
        """
        assert drift_resistance([0.0, 0.0, 0.0]) == 0.0
        assert not is_measurable([0.0, 0.0, 0.0])

    def test_single_cycle_is_unmeasurable_not_perfect(self) -> None:
        """One cycle cannot exhibit drift; it must not be a source of free score.

        Regression: previously returned 1.0, so ``--drift-cycles 0`` handed a
        submitter 30% of elite_score for running strictly less of the benchmark.
        """
        assert drift_resistance([0.5]) == 0.0
        assert not is_measurable([0.5])

    def test_empty_input_is_unmeasurable(self) -> None:
        assert drift_resistance([]) == 0.0
        assert not is_measurable([])

    def test_min_cycles_constant_matches_behaviour(self) -> None:
        scores = [0.8] * MIN_CYCLES_FOR_DRIFT
        assert is_measurable(scores)
        assert not is_measurable(scores[:-1])


class TestRetentionRatio:
    def test_flat_scores_retain_everything(self) -> None:
        assert drift_resistance([0.7, 0.7, 0.7]) == 1.0

    def test_halved_score_retains_half(self) -> None:
        assert drift_resistance([0.8, 0.4, 0.4]) == pytest.approx(0.5)

    def test_ratio_uses_mean_of_later_cycles(self) -> None:
        # mean(0.6, 0.4) = 0.5, baseline 1.0 → 0.5
        assert drift_resistance([1.0, 0.6, 0.4]) == pytest.approx(0.5)

    def test_total_collapse_is_zero(self) -> None:
        assert drift_resistance([1.0, 0.0, 0.0]) == 0.0

    def test_improvement_clamps_at_one(self) -> None:
        """Scoring better after re-compaction means nothing was lost.

        Left unclamped, noise on a weak baseline would buy ranking weight —
        ``[0.1, 0.9]`` would otherwise report 9.0.
        """
        assert drift_resistance([0.5, 0.9, 1.0]) == 1.0
        assert drift_resistance([0.1, 0.9]) == 1.0

    @pytest.mark.parametrize(
        "scores",
        [[0.9, 0.4, 0.2], [1.0, 1.0], [0.3, 0.0], [0.05, 0.9, 0.01]],
    )
    def test_always_in_unit_interval(self, scores: list[float]) -> None:
        assert 0.0 <= drift_resistance(scores) <= 1.0

    def test_a_strong_stable_method_beats_a_weak_stable_one_only_on_overall(self) -> None:
        """Drift resistance is deliberately scale-free — it measures retention.

        Both of these retain 100% of what they captured, so both score 1.0 here.
        That is correct for *this* metric; absolute quality is what
        ``overall_score`` measures, and ``elite_score`` weights both. The bug
        being guarded against is the zero-baseline case above, not this one.
        """
        assert drift_resistance([0.9, 0.9]) == drift_resistance([0.1, 0.1]) == 1.0
