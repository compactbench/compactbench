"""Cross-cycle drift metrics.

Given per-cycle scores ``[c0, c1, c2, ...]``, we compute how much scores
degrade after the initial cycle. A method that holds steady scores 1.0;
a method that degrades scores proportionally lower.
"""

from __future__ import annotations


def drift_deltas(cycle_scores: list[float]) -> list[float]:
    """Return ``[c_n - c_0 for n >= 1]``. Empty list for ``len < 2``."""
    if len(cycle_scores) < 2:
        return []
    baseline = cycle_scores[0]
    return [s - baseline for s in cycle_scores[1:]]


def drift_resistance(cycle_scores: list[float]) -> float:
    """Clamp of ``1 + mean(drift_deltas)`` into ``[0.0, 1.0]``.

    A method with stable scores returns 1.0. A method that degrades 20%
    per cycle on average returns 0.8. A method that improves returns 1.0
    (clamped — improvement does not extend beyond perfect drift resistance).
    """
    deltas = drift_deltas(cycle_scores)
    if not deltas:
        return 1.0
    avg = sum(deltas) / len(deltas)
    return max(0.0, min(1.0, 1.0 + avg))
