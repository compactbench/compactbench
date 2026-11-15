"""``compactbench check``: a small, repeatable Practice run for CI.

The check runs a fixed sample of the public Practice suite (the same cases every
time, chosen by the seed group), summarizes it as Markdown, and compares it with a
saved baseline so a pull request that makes a method forget more fails its build.

A baseline is the JSON this module writes with :func:`snapshot`. Two snapshots are
only comparable when they were taken on the same cases, budget, reader and scorer;
:func:`compare` refuses anything else rather than report a misleading change.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from compactbench.contracts.result import RunResult

SNAPSHOT_SCHEMA = 1
MARKER = "<!-- compactbench-check"
"""Starts the report's first line when ``marker=True``, so a CI job can find and update
its own pull-request comment (one per method and model)."""

# Settings that must match for a score change to mean anything.
_COMPARABLE = (
    "suite",
    "difficulty",
    "drift_cycles",
    "cases",
    "seed_group",
    "budget_tokens",
    "reader",
    "scorer",
)


def snapshot(result: RunResult) -> dict[str, Any]:
    """The comparable summary of a run, as saved in a baseline file."""
    m = result.metrics
    reader = f"{result.reader_provider}/{result.reader_model}"
    if result.reader_effort:
        reader += f"@{result.reader_effort}"
    return {
        "schema": SNAPSHOT_SCHEMA,
        "method": result.method_name,
        "method_version": result.method_version,
        "model": f"{result.compactor_provider}/{result.compactor_model}",
        "suite": f"{result.suite}@{result.suite_version}",
        "difficulty": result.difficulty,
        "drift_cycles": result.drift_cycles,
        "cases": len(result.cases),
        "seed_group": result.seed_group,
        "budget_tokens": result.budget_tokens,
        "reader": reader,
        "scorer": result.scorer_version,
        "score": round(m.score, 4),
        "score_ci_low": round(m.score_ci_low, 4),
        "score_ci_high": round(m.score_ci_high, 4),
        "by_cycle": [round(s, 4) for s in m.by_cycle],
        "by_family": {k: round(v.score, 4) for k, v in sorted(m.by_family.items())},
        "reader_error_rate": round(m.reader_error_rate, 4),
    }


def load_snapshot(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict) or data.get("schema") != SNAPSHOT_SCHEMA:  # pyright: ignore[reportUnknownMemberType]
        raise ValueError(f"{path} is not a compactbench check baseline (schema {SNAPSHOT_SCHEMA})")
    return data  # pyright: ignore[reportUnknownVariableType]


def save_snapshot(path: Path, snap: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snap, indent=2) + "\n", encoding="utf-8")


@dataclass
class Verdict:
    passed: bool
    change: float | None = None
    """Score minus baseline score (0-1 scale), when there is a comparable baseline."""
    reasons: list[str] = field(default_factory=list[str])
    mismatch: list[str] = field(default_factory=list[str])
    """Settings that differ from the baseline; non-empty means no comparison was made."""


def compare(
    current: dict[str, Any],
    baseline: dict[str, Any] | None,
    *,
    max_drop: float | None,
    min_score: float | None,
) -> Verdict:
    """Apply the gates. ``max_drop`` and ``min_score`` are in points (0-100)."""
    verdict = Verdict(passed=True)
    if baseline is not None:
        verdict.mismatch = [
            f"{key}: baseline {baseline.get(key)!r}, now {current.get(key)!r}"
            for key in _COMPARABLE
            if baseline.get(key) != current.get(key)
        ]
        if verdict.mismatch:
            verdict.passed = False
            verdict.reasons.append(
                "the baseline was recorded with different settings, so the scores are not "
                "comparable; re-record it with --update-baseline"
            )
        else:
            change = float(current["score"]) - float(baseline["score"])
            verdict.change = change
            if max_drop is not None and -change * 100 > max_drop + 1e-9:
                verdict.passed = False
                verdict.reasons.append(
                    f"score dropped {-change * 100:.1f} points (limit {max_drop:.1f})"
                )
    if min_score is not None and current["score"] * 100 < min_score - 1e-9:
        verdict.passed = False
        verdict.reasons.append(
            f"score {current['score'] * 100:.1f} is below the minimum {min_score:.1f}"
        )
    return verdict


def _pts(value: float) -> str:
    return f"{value * 100:.1f}"


def _interval(snap: dict[str, Any]) -> str:
    # The interval is a bootstrap over cases: one case has no spread to measure.
    if snap["cases"] < 2:
        return "-"
    return f"{_pts(snap['score_ci_low'])}-{_pts(snap['score_ci_high'])}"


def _delta(value: float | None) -> str:
    if value is None:
        return "—"
    points = value * 100
    if abs(points) < 0.05:
        return "0.0"
    return f"{'+' if points > 0 else '-'}{abs(points):.1f}"


def render_markdown(
    current: dict[str, Any],
    baseline: dict[str, Any] | None,
    verdict: Verdict,
    *,
    max_drop: float | None,
    min_score: float | None,
    marker: bool = False,
    recorded: bool = False,
) -> str:
    """The check's report: one table for the headline, one per family."""
    comparable = baseline is not None and not verdict.mismatch
    status = "passed" if verdict.passed else "failed"
    lines: list[str] = []
    if marker:
        lines.append(f"{MARKER} {current['method']} {current['model']} -->")
    lines.append(f"### CompactBench check: {status}")
    lines.append("")
    budget = current["budget_tokens"]
    budget_text = f"{budget:,}-token budget" if budget else "no budget"
    lines.append(
        f"**{current['method']}** ({current['method_version']}) on `{current['model']}` · "
        f"{current['suite']} at {current['difficulty']}, {current['cases']} "
        f"{'case' if current['cases'] == 1 else 'cases'} "
        f"(seed group `{current['seed_group']}`), {current['drift_cycles'] + 1} compactions, "
        f"{budget_text} · reader `{current['reader']}`"
    )
    lines.append("")
    if comparable:
        assert baseline is not None
        lines.append("| | Score | 95% interval | Baseline | Change |")
        lines.append("|---|---:|---:|---:|---:|")
        lines.append(
            f"| Overall | **{_pts(current['score'])}** | {_interval(current)} | "
            f"{_pts(baseline['score'])} | "
            f"{_delta(verdict.change)} |"
        )
    else:
        lines.append("| | Score | 95% interval |")
        lines.append("|---|---:|---:|")
        lines.append(f"| Overall | **{_pts(current['score'])}** | {_interval(current)} |")
    lines.append("")
    if current["by_cycle"]:
        lines.append(
            "Score after each compaction: " + " → ".join(_pts(s) for s in current["by_cycle"])
        )
        lines.append("")
    families: dict[str, float] = current["by_family"]
    if families:
        lines.append("#### By family")
        lines.append("")
        if comparable:
            assert baseline is not None
            before: dict[str, float] = baseline.get("by_family", {})
            lines.append("| Family | Score | Baseline | Change |")
            lines.append("|---|---:|---:|---:|")
            for key, value in families.items():
                old = before.get(key)
                lines.append(
                    f"| `{key}` | {_pts(value)} | {_pts(old) if old is not None else '—'} | "
                    f"{_delta(value - old if old is not None else None)} |"
                )
        else:
            lines.append("| Family | Score |")
            lines.append("|---|---:|")
            for key, value in families.items():
                lines.append(f"| `{key}` | {_pts(value)} |")
        lines.append("")
    gates: list[str] = []
    if baseline is not None and max_drop is not None:
        gates.append(f"no more than {max_drop:.1f} points below the baseline")
    if min_score is not None:
        gates.append(f"at least {min_score:.1f}")
    if recorded:
        lines.append("Recorded as the new baseline.")
    if gates:
        lines.append(f"Gate: {' and '.join(gates)}.")
    elif baseline is None and not recorded:
        lines.append("No baseline yet: record one with `--update-baseline` to catch regressions.")
    for reason in verdict.reasons:
        lines.append(f"- **Failed:** {reason}.")
    for item in verdict.mismatch:
        lines.append(f"  - {item}")
    if current["reader_error_rate"] > 0:
        lines.append(
            f"- Note: the reader failed on {current['reader_error_rate']:.0%} of questions "
            "(provider errors or unparseable answers), which lowers the score."
        )
    lines.append("")
    return "\n".join(lines)
