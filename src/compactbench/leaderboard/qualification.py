"""Qualification floors: what a run must satisfy before it can be ranked."""

from __future__ import annotations

from dataclasses import dataclass, field

from compactbench.compactors import CONTROL_KEYS
from compactbench.contracts import RunResult
from compactbench.leaderboard.season import Season, season_mismatches
from compactbench.runner.persistence import INCOMPLETE_RUN_NOTE

#: More unparsable reader replies than this means the run measured the reader,
#: not the method.
MAX_READER_ERROR_RATE: float = 0.05


@dataclass(frozen=True)
class QualificationResult:
    """Outcome of checking a run against the leaderboard floors."""

    qualified: bool
    reasons: list[str] = field(default_factory=list[str])


def qualify(run: RunResult, *, season: Season | None = None) -> QualificationResult:
    """Check ``run`` against the floors (and its season, when given)."""
    reasons: list[str] = []

    # Controls are reference rows. Ranking the oracle — which sees the whole
    # conversation — against compaction methods is a category error, and the
    # null arm exists to expose the floor, not to place on the board.
    if run.method_name in CONTROL_KEYS:
        reasons.append(
            f"{run.method_name!r} is a control arm — published as a reference row, never ranked"
        )

    if INCOMPLETE_RUN_NOTE in run.notes:
        reasons.append(
            "run is incomplete (no run_end event): its scores cover only the cases that "
            "finished — re-run to completion or use --resume"
        )

    if not run.cases:
        reasons.append("no cases completed")

    if run.drift_cycles < 1:
        reasons.append(
            "run has no drift cycles — multi-cycle retention is what the benchmark ranks on"
        )

    if run.budget_tokens is None:
        reasons.append("run had no token budget — ranked runs compact to a fixed budget")
    elif run.metrics.budget_violations:
        reasons.append(
            f"{run.metrics.budget_violations} cycle(s) produced an artifact over the "
            f"{run.budget_tokens}-token budget"
        )

    if run.metrics.reader_error_rate > MAX_READER_ERROR_RATE:
        reasons.append(
            f"reader gave no usable answer for {run.metrics.reader_error_rate:.1%} of probes "
            f"(max {MAX_READER_ERROR_RATE:.0%})"
        )

    if run.reader_endpoint_kind != "default":
        reasons.append(
            "the reader ran against a custom endpoint — ranked runs use the provider's own"
        )

    if season is not None:
        reasons.extend(season_mismatches(run, season))

    return QualificationResult(qualified=not reasons, reasons=reasons)
