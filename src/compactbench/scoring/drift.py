"""Cross-cycle drift metrics.

Drift resistance answers one question: **how much of what a method captured on
the first compaction survives repeated re-compaction?** It is the metric the
whole benchmark is built around, and it carries 30% of ``elite_score``.

The original definition was ``clamp(1 + mean(score[n] - score[0]))`` — additive
distance from the first cycle. That is degenerate in the case that matters most:
it measures only whether scores *change*, not whether they are any good, so a
method scoring 0.0 on every single cycle is perfectly stable and scored a
**perfect 1.0**. Consistent total failure was the highest-scoring outcome on the
benchmark's headline metric, and it collected 30% of the ranking weight for free.

The definition here is a retention *ratio* — the fraction of the first cycle's
score that later cycles keep — with the degenerate inputs called out rather than
silently rewarded:

============================  ==================  ============================
cycle scores                  drift_resistance    reading
============================  ==================  ============================
``[0.8, 0.8, 0.8]``           ``1.00``            holds everything
``[0.8, 0.6, 0.4]``           ``0.62``            loses ~40% by cycle 2
``[0.4, 0.8]``                ``1.00``            improvement clamps at 1.0
``[0.0, 0.0, 0.0]``           ``0.00``            nothing to retain (was 1.00)
``[0.8]``                     ``0.00``            unmeasurable — see below
============================  ==================  ============================

A single cycle cannot exhibit drift, so drift resistance is *undefined* there
rather than perfect. It returns ``0.0`` so it can never be a source of free
score, and :func:`is_measurable` lets callers render "n/a" instead of a
misleading ``0.000``. Qualification separately refuses to rank any run that did
not execute enough cycles to measure drift at all.
"""

from __future__ import annotations

#: Cycles required before drift can be measured at all: one baseline + one
#: re-compaction. Runs below this are unrankable rather than perfect-scoring.
MIN_CYCLES_FOR_DRIFT = 2


def drift_deltas(cycle_scores: list[float]) -> list[float]:
    """Return ``[c_n - c_0 for n >= 1]``. Empty list for ``len < 2``.

    Retained as a diagnostic: the raw per-cycle deltas are what you want when
    inspecting *where* a method fell over, as opposed to the single summary
    number :func:`drift_resistance` reports.
    """
    if len(cycle_scores) < MIN_CYCLES_FOR_DRIFT:
        return []
    baseline = cycle_scores[0]
    return [s - baseline for s in cycle_scores[1:]]


def is_measurable(cycle_scores: list[float]) -> bool:
    """True when ``cycle_scores`` can support a meaningful drift number.

    Requires at least two cycles (something to drift *from* and *to*) and a
    non-zero baseline (something to retain). Callers should display "n/a"
    rather than a numeric drift resistance when this is False.
    """
    return len(cycle_scores) >= MIN_CYCLES_FOR_DRIFT and cycle_scores[0] > 0.0


def drift_resistance(cycle_scores: list[float]) -> float:
    """Fraction of the first cycle's score retained by later cycles, in ``[0, 1]``.

    ``mean(cycle_scores[1:]) / cycle_scores[0]``, clamped. Improvement clamps to
    1.0 — a method that scores better after re-compaction has lost nothing, and
    letting it exceed 1.0 would let noise buy ranking weight.

    Returns ``0.0`` when drift is not measurable (fewer than two cycles, or a
    zero baseline). See :func:`is_measurable`; the module docstring explains why
    that is deliberately not ``1.0``.
    """
    if not is_measurable(cycle_scores):
        return 0.0
    baseline = cycle_scores[0]
    later = cycle_scores[1:]
    retained = (sum(later) / len(later)) / baseline
    return max(0.0, min(1.0, retained))
