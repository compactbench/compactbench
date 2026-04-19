"""Qualification floor checks for leaderboard entries.

Floors locked in docs/architecture/decisions.md §B4.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from compactbench.contracts import RunResult
from compactbench.leaderboard.ranking import TIER_FLOORS, CompressionTier

MAX_CONTRADICTION_RATE: float = 0.10
MIN_FAMILY_MEAN_SCORE: float = 0.40


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

    tier_floor = TIER_FLOORS[tier]
    if run_result.compression_ratio < tier_floor:
        reasons.append(
            f"compression {run_result.compression_ratio:.2f}x is below the {tier} "
            f"floor of {tier_floor:.1f}x"
        )

    if run_result.contradiction_rate > MAX_CONTRADICTION_RATE:
        reasons.append(
            f"contradiction_rate {run_result.contradiction_rate:.3f} exceeds the "
            f"{MAX_CONTRADICTION_RATE:.2f} maximum"
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
