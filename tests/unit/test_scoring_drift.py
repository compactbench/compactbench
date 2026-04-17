"""Drift-metric tests."""

from __future__ import annotations

import pytest

from compactbench.scoring import drift_deltas, drift_resistance

pytestmark = pytest.mark.unit


def test_single_cycle_has_no_deltas() -> None:
    assert drift_deltas([0.9]) == []


def test_deltas_are_relative_to_cycle_zero() -> None:
    assert drift_deltas([1.0, 0.8, 0.6]) == pytest.approx([-0.2, -0.4])


def test_resistance_single_cycle_is_one() -> None:
    assert drift_resistance([0.5]) == 1.0


def test_resistance_flat_is_one() -> None:
    assert drift_resistance([0.7, 0.7, 0.7]) == 1.0


def test_resistance_degrades_proportionally() -> None:
    # mean delta = -0.2 → 1 + (-0.2) = 0.8
    assert drift_resistance([1.0, 0.8, 0.8]) == pytest.approx(0.8)


def test_resistance_clamped_at_zero_on_total_collapse() -> None:
    assert drift_resistance([1.0, 0.0, 0.0]) == 0.0


def test_resistance_clamped_at_one_on_improvement() -> None:
    # Improvement above baseline shouldn't exceed 1.0.
    assert drift_resistance([0.5, 0.9, 1.0]) == 1.0


def test_resistance_in_unit_interval() -> None:
    assert 0.0 <= drift_resistance([0.9, 0.4, 0.2]) <= 1.0


def test_empty_input_is_one() -> None:
    assert drift_resistance([]) == 1.0
