"""Item analysis: which question templates are valid, hard, and tell methods apart.

    uv run python scripts/item_analysis.py .local/results/s1-claude-haiku-5-5/*.jsonl \
        --calibration .local/calibration/s1-calibration.jsonl \
        --out .local/calibration/item-analysis.md

Reads RAW results files (with real probe keys — published files are redacted and
can't be analysed this way), one per method. Probes are grouped by template
(``family/category/<first word of the key>``, e.g. ``entity_confusion/role``) because
every run samples its own names. Per template: how often it appears, the mean score
over all methods, each method's mean, the discrimination (correlation between a
method's score on the template and its overall score), and — from a calibration run
with controls — the oracle and null scores. Output stays in ``.local/``: template names
come from the private families.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean

from compactbench.contracts import ProbeResult
from compactbench.runner import to_run_result
from compactbench.scoring.answers import Arm


def item_score(r: ProbeResult, arm: Arm = "score") -> float | None:
    """A probe's score for item statistics. Abstention probes ("not stated") count as
    1 when the reader abstained and 0 when it answered — unlike the leaderboard, which
    only counts their misses, so an item's correct rate is visible here."""
    value: float | None = getattr(r, arm)
    if value is None:
        return None
    return 1.0 if r.expects_abstention and value >= 1.0 else value


def template(key: str, category: str) -> str:
    family, _, rest = key.partition("/")
    return f"{family}/{category}/{rest.split('_', 1)[0]}"


def pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 3:
        return None
    mx, my = mean(xs), mean(ys)
    sx = sum((x - mx) ** 2 for x in xs) ** 0.5
    sy = sum((y - my) ** 2 for y in ys) ** 0.5
    if not sx or not sy:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True)) / (sx * sy)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("results", type=Path, nargs="+")
    parser.add_argument("--calibration", type=Path)
    parser.add_argument("--out", type=Path, default=Path(".local/calibration/item-analysis.md"))
    args = parser.parse_args()

    per_method: dict[str, dict[str, list[float]]] = {}
    overall: dict[str, float] = {}
    family_scores: dict[str, dict[str, float]] = {}
    for path in args.results:
        run = to_run_result(path)
        if not run.cases:
            continue
        name = run.method_name
        overall[name] = run.metrics.score
        family_scores[name] = {k: v.score for k, v in run.metrics.by_family.items()}
        by_template: dict[str, list[float]] = defaultdict(list)
        for case in run.cases:
            for cycle in case.cycles:
                for r in cycle.probe_results:
                    if (v := item_score(r)) is not None:
                        by_template[template(r.key, r.category)].append(v)
        per_method[name] = by_template

    oracle: dict[str, list[float]] = defaultdict(list)
    null: dict[str, list[float]] = defaultdict(list)
    if args.calibration:
        for case in to_run_result(args.calibration).cases:
            for cycle in case.cycles:
                for r in cycle.probe_results:
                    t = template(r.key, r.category)
                    if (v := item_score(r, "oracle_score")) is not None:
                        oracle[t].append(v)
                    if (v := item_score(r, "null_score")) is not None:
                        null[t].append(v)

    methods = sorted(overall, key=lambda m: -overall[m])
    templates = sorted({t for m in per_method.values() for t in m})
    rows: list[dict[str, object]] = []
    for t in templates:
        means = {m: mean(per_method[m][t]) for m in methods if per_method[m].get(t)}
        n = sum(len(per_method[m].get(t, [])) for m in methods)
        ms = [m for m in means if len(per_method[m][t]) >= 5]
        r = pearson([means[m] for m in ms], [overall[m] for m in ms])
        o = mean(oracle[t]) if oracle.get(t) else None
        z = mean(null[t]) if null.get(t) else None
        p = mean([s for m in methods for s in per_method[m].get(t, [])]) if n else 0.0
        flags = []
        if o is not None and o < 0.9:
            flags.append("oracle<0.90")
        if z is not None and z > 0.1 and "abstention" not in t:
            flags.append("null>0.10")
        if p > 0.95 and "abstention" not in t:
            flags.append("ceiling")
        if r is not None and r < 0.1 and "abstention" not in t:
            flags.append("low-discrimination")
        rows.append(
            {
                "template": t,
                "n": n,
                "p": p,
                "r": r,
                "oracle": o,
                "null": z,
                "means": means,
                "flags": flags,
            }
        )

    fmt = lambda v: "—" if v is None else f"{v:.2f}"  # noqa: E731
    lines = [
        "# Item analysis (private)",
        "",
        f"Methods (overall score): {', '.join(f'{m} {overall[m]:.3f}' for m in methods)}",
        "",
        "## Families: best baseline vs others",
        "",
        "| family | " + " | ".join(methods) + " |",
        "|---|" + "---|" * len(methods),
    ]
    families = sorted({f for s in family_scores.values() for f in s})
    for f in families:
        lines.append(f"| {f} | " + " | ".join(fmt(family_scores[m].get(f)) for m in methods) + " |")
    best = methods[0] if methods else None
    if best:
        top = family_scores[best]
        lines += [
            "",
            f"Best baseline `{best}`: highest family {max(top.values()):.2f}, lowest "
            f"{min(top.values()):.2f}, spread {max(top.values()) - min(top.values()):.2f} "
            f"(gate as revised: no family above 0.85).",
        ]
    lines += [
        "",
        "## Templates",
        "",
        "p = mean score over all methods; r = discrimination (corr. with overall score, "
        "methods with ≥5 instances); oracle/null from calibration.",
        "",
        "| template | n | p | r | oracle | null | flags |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in sorted(rows, key=lambda x: x["template"]):
        lines.append(
            f"| {row['template']} | {row['n']} | {fmt(row['p'])} | {fmt(row['r'])} | "  # type: ignore[arg-type]
            f"{fmt(row['oracle'])} | {fmt(row['null'])} | {', '.join(row['flags']) or ''} |"  # type: ignore[arg-type]
        )
    flagged = [r for r in rows if r["flags"]]
    lines += ["", f"{len(flagged)} of {len(rows)} templates flagged."]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    args.out.with_suffix(".json").write_text(
        json.dumps(rows, indent=1, default=float) + "\n", encoding="utf-8"
    )
    print(f"wrote {args.out} — {len(rows)} templates, {len(flagged)} flagged")
    return 0


if __name__ == "__main__":
    sys.exit(main())
