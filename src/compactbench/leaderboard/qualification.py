"""Qualification floor checks for leaderboard entries.

Floors locked in docs/architecture/decisions.md §B4.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from compactbench.compactors import CONTROL_KEYS
from compactbench.contracts import RunResult
from compactbench.leaderboard.ranking import TIER_FLOORS, CompressionTier
from compactbench.runner.persistence import INCOMPLETE_RUN_NOTE
from compactbench.scoring.drift import MIN_CYCLES_FOR_DRIFT

MAX_CONTRADICTION_RATE: float = 0.10
MIN_FAMILY_MEAN_SCORE: float = 0.40

#: Compression above this is not a compaction result, it is an empty artifact.
#: Real methods land in the 2-20x band. The ``null`` control — which returns
#: nothing at all — measures ~450x on the shipped suites and, before this floor
#: existed, cleared every tier and collected the full compression bonus while
#: retaining no information whatsoever. Anything past this bound is reported as
#: degenerate rather than excellent.
MAX_PLAUSIBLE_COMPRESSION: float = 50.0


@dataclass(frozen=True)
class QualificationResult:
    """Outcome of checking a run against leaderboard qualification floors."""

    qualified: bool
    reasons: list[str] = field(default_factory=list[str])


def qualify(
    run_result: RunResult,
    *,
    tier: CompressionTier,
    expected_drift_cycles: int,
) -> QualificationResult:
    """Check a :class:`RunResult` against the leaderboard floors.

    Returns a :class:`QualificationResult` — inspect ``reasons`` when
    ``qualified`` is ``False`` to learn why.
    """
    reasons: list[str] = []

    # Control arms are reference rows, never competitors. `oracle` bounds the
    # top of the range and `null` the bottom; ranking either against submitted
    # methods would be a category error, and `null` in particular would place
    # well on a leaderboard it exists to expose the limits of.
    if run_result.method_name in CONTROL_KEYS:
        reasons.append(
            f"{run_result.method_name!r} is a control arm, not a submittable method — "
            f"controls are published as reference rows and are never ranked"
        )

    tier_floor = TIER_FLOORS[tier]
    if run_result.compression_ratio < tier_floor:
        reasons.append(
            f"compression {run_result.compression_ratio:.2f}x is below the {tier} "
            f"floor of {tier_floor:.1f}x"
        )

    if run_result.compression_ratio > MAX_PLAUSIBLE_COMPRESSION:
        reasons.append(
            f"compression {run_result.compression_ratio:.1f}x exceeds the plausible maximum of "
            f"{MAX_PLAUSIBLE_COMPRESSION:.0f}x — an artifact this small is almost certainly "
            f"empty or degenerate rather than a compaction result"
        )

    # Drift resistance is 30% of elite_score. A run that never executed a second
    # cycle has not measured it, so it cannot be ranked on it — previously such
    # a run scored a perfect 1.0 on the metric and `--drift-cycles 0` was simply
    # the cheapest way to a high score.
    if expected_drift_cycles + 1 < MIN_CYCLES_FOR_DRIFT:
        reasons.append(
            f"run configured with {expected_drift_cycles} drift cycle(s); at least "
            f"{MIN_CYCLES_FOR_DRIFT - 1} is required before drift resistance is measurable"
        )

    if run_result.contradiction_rate > MAX_CONTRADICTION_RATE:
        reasons.append(
            f"contradiction_rate {run_result.contradiction_rate:.3f} exceeds the "
            f"{MAX_CONTRADICTION_RATE:.2f} maximum"
        )

    # A results file with no run_end event is a crashed or in-flight run. Its
    # aggregates cover only the cases that happened to finish, so ranking it
    # would both publish an unrepresentative number and make "stop the run once
    # the easy cases are through" a viable strategy.
    if INCOMPLETE_RUN_NOTE in run_result.notes:
        reasons.append(
            "run is incomplete (no run_end event): aggregates cover only the cases that "
            "finished, so the run cannot be ranked — re-run it to completion, or use --resume"
        )

    if not run_result.cases:
        reasons.append("no cases completed")
    else:
        expected_cycles = expected_drift_cycles + 1
        for case in run_result.cases:
            if len(case.cycles) < expected_cycles:
                reasons.append(
                    f"case {case.case_id!r} completed only {len(case.cycles)} of "
                    f"{expected_cycles} configured cycles"
                )

    # Per-family mean-score guard only applies when the run covers more than one family.
    # Named "mean score" rather than "pass rate" because it is a weighted mean of
    # case_scores, not a fraction of cases above a binary pass threshold.
    family_means = _family_mean_scores(run_result)
    if len(family_means) > 1:
        for family, mean_score in family_means.items():
            if mean_score < MIN_FAMILY_MEAN_SCORE:
                reasons.append(
                    f"family {family!r} mean score {mean_score:.2f} is below the "
                    f"{MIN_FAMILY_MEAN_SCORE:.2f} minimum (category-diversity guard)"
                )

    return QualificationResult(qualified=not reasons, reasons=reasons)


def _family_mean_scores(run_result: RunResult) -> dict[str, float]:
    """Mean case_score grouped by benchmark family inferred from template_key."""
    groups: dict[str, list[float]] = {}
    for case in run_result.cases:
        family = _infer_family(case.template_key)
        groups.setdefault(family, []).append(case.case_score)
    return {family: sum(scores) / len(scores) for family, scores in groups.items() if scores}


def _infer_family(template_key: str) -> str:
    """Infer family name from template key by stripping trailing ``_starter_v<N>`` or ``_v<N>``."""
    for suffix_prefix in ("_starter_v", "_elite_v", "_v"):
        idx = template_key.rfind(suffix_prefix)
        if idx > 0:
            return template_key[:idx]
    return template_key
