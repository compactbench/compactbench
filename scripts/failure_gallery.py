"""Pick real compaction failures from public Practice runs for the site's failure gallery.

    uv run python scripts/failure_gallery.py .local/traces/practice/*.traces.jsonl \
        --results-dir .local/calibration/practice --out docs/data/failure-gallery.json

Only public suites are allowed (the script refuses anything else): the gallery shows
conversation text. An example is kept only when the compaction lost the answer — the
expected answer appears nowhere in what the reader saw — so every example is the
method's failure, not the reader's. Per family it prefers a stale answer (a superseded
value kept), then a decoy picked, then a dropped fact, from later compactions first.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from compactbench.contracts import GeneratedCase, Probe
from compactbench.runner.persistence import read_run_start
from compactbench.scenarios import get_family
from compactbench.scenarios.generate import expand_suite, get_suite

PUBLIC_SUITES = {"starter", "practice", "drills"}
KIND_ORDER = {"stale": 0, "trap": 1, "dropped": 2, "wrong": 3}
KIND_TEXT = {
    "stale": "Kept the superseded value",
    "trap": "Picked a decoy",
    "dropped": "Lost the fact",
    "wrong": "Wrong answer",
}
_LETTER = re.compile(r"^\(?([A-Za-z])\)?[.)]?$")


def as_options(probe: Probe, raw: object) -> list[str]:
    """The reader's answer as text: option letters mapped to their option."""
    picks = raw if isinstance(raw, list) else [raw]
    out: list[str] = []
    for pick in picks:
        text = str(pick).strip()
        m = _LETTER.match(text)
        if probe.options and m and 0 <= ord(m.group(1).upper()) - 65 < len(probe.options):
            out.append(probe.options[ord(m.group(1).upper()) - 65])
        elif text:
            out.append("Not stated" if text.upper() == "NOT_STATED" else text)
    return out


def excerpt(text: str, needle: str, width: int = 220, at: int | None = None) -> dict[str, str]:
    i = text.lower().find(needle.lower()) if at is None else at
    start, end = max(0, i - width), min(len(text), i + len(needle) + width)
    return {
        "before": ("…" if start else "") + text[start:i],
        "match": text[i : i + len(needle)],
        "after": text[i + len(needle) : end] + ("…" if end < len(text) else ""),
    }


def anchors(question: str) -> set[str]:
    """Names and identifiers in a question (capitalised words after the first, words with
    digits): the turn that states the answer must mention all of them."""
    out: set[str] = set()
    for n, raw in enumerate(re.findall(r"[A-Za-z0-9][A-Za-z0-9-]*(?:'s)?", question)):
        word = raw.removesuffix("'s")
        if (n > 0 and word[:1].isupper()) or any(c.isdigit() for c in word):
            out.add(word.lower())
    return out


def _occurrences(text: str, needle: str) -> list[int]:
    """Whole-word positions of ``needle`` in ``text`` (case-insensitive)."""
    pattern = rf"(?<![A-Za-z0-9_]){re.escape(needle)}(?![A-Za-z0-9_])"
    return [m.start() for m in re.finditer(pattern, text, re.IGNORECASE)] if needle else []


def source_turn(case: GeneratedCase, probe: Probe, asked_at: int) -> dict[str, Any] | None:
    """Where the conversation states an expected answer: of every whole-word occurrence,
    up to the cycle asked at, in a turn that mentions every name and identifier in the
    question, the one with most of the question's words close by, then nearest a name or
    identifier, then from the cycle the fact was introduced in — so a log line or another
    ticket that happens to match doesn't win."""
    required = anchors(probe.question)
    words = {
        w.lower() for w in re.findall(r"[A-Za-z0-9][A-Za-z0-9-]{3,}", probe.question)
    } | required
    best: tuple[tuple[int, int, int, int], dict[str, Any]] | None = None
    for spec in case.cycles[: asked_at + 1]:
        for turn in spec.turns:
            low = turn.content.lower()
            if not all(a in low for a in required):
                continue
            marks = [m for a in required for m in _occurrences(low, a)]
            for needle in probe.answer:
                for pos in _occurrences(turn.content, needle):
                    near = low[max(0, pos - 160) : pos + len(needle) + 160]
                    distance = min((abs(pos - m) for m in marks), default=0)
                    rank = (
                        sum(w in near for w in words),
                        -distance,
                        int(spec.cycle == probe.origin_cycle),
                        turn.id,
                    )
                    if best is None or rank > best[0]:
                        found = {"compaction": spec.cycle + 1, "role": turn.role.value}
                        best = (rank, found | excerpt(turn.content, needle, at=pos))
    return best[1] if best else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("traces", type=Path, nargs="+")
    parser.add_argument("--results-dir", type=Path, required=True)
    parser.add_argument("--per-family", type=int, default=2)
    parser.add_argument(
        "--skip", action="append", default=[], help="Leave out questions containing this text."
    )
    parser.add_argument("--out", type=Path, default=Path("docs/data/failure-gallery.json"))
    args = parser.parse_args()

    candidates: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for trace in args.traces:
        method = trace.name.removesuffix(".traces.jsonl")
        start = read_run_start(args.results_dir / f"{method}.jsonl")
        if start is None or start.suite not in PUBLIC_SUITES:
            print(f"refusing {trace}: not a public suite run", file=sys.stderr)
            return 1
        suite = get_suite(start.suite)
        cases = {
            c.case_id: c
            for c in expand_suite(
                suite,
                seed_group=start.seed_group,
                cases_per_family=start.cases_per_family,
                drift_cycles=start.drift_cycles,
            )
        }
        with trace.open(encoding="utf-8") as fp:
            for line in fp:
                rec = json.loads(line)
                case = cases.get(rec["case_id"])
                if case is None:
                    continue
                context = rec["visible_context"].lower()
                probes = {p["key"]: Probe.model_validate(p) for p in rec["probes"]}
                for r in rec["result"]["probe_results"]:
                    if r["score"] > 0 or r["expects_abstention"]:
                        continue
                    probe = probes[r["key"]]
                    if any(text.lower() in probe.question.lower() for text in args.skip):
                        continue
                    if any(a.lower() in context for a in probe.answer if a):
                        continue  # the answer survived: a reader miss, not a compaction failure
                    reader = as_options(probe, rec["answers"].get(probe.key))
                    if any(_LETTER.match(a) for a in reader):
                        continue  # an option letter that doesn't exist: nothing to show
                    if r["stale"]:
                        kind = "stale"
                    elif r["trapped"]:
                        kind = "trap"
                    elif r["abstained"] or not reader:
                        kind = "dropped"
                    else:
                        kind = "wrong"
                    source = source_turn(case, probe, rec["cycle"])
                    if source is None:
                        continue
                    kept = None
                    for value in [*probe.stale, *probe.traps]:
                        if value and value.lower() in context and value in reader:
                            kept = excerpt(rec["visible_context"], value, 160)
                            break
                    family = probe.family or case.family
                    candidates[family].append(
                        {
                            "family": family,
                            "family_title": get_family(family).title,
                            "kind": kind,
                            "kind_text": KIND_TEXT[kind],
                            "method": method,
                            "compaction": rec["cycle"] + 1,
                            "said_at": probe.origin_cycle + 1,
                            "question": probe.question,
                            "expected": probe.answer,
                            "answered": reader or ["(no answer)"],
                            "source": source,
                            "artifact": kept,
                            "artifact_tokens": rec["result"]["artifact_tokens"],
                        }
                    )

    gallery: list[dict[str, Any]] = []
    for family in sorted(candidates):
        ranked = sorted(
            candidates[family],
            key=lambda x: (
                KIND_ORDER[x["kind"]],
                x["method"] == "extractive",  # model-made summaries first
                -(x["compaction"] - x["said_at"]),
                x["method"],
            ),
        )
        seen_kinds: set[str] = set()
        seen_methods: set[str] = set()
        for ex in ranked:
            if len([g for g in gallery if g["family"] == family]) >= args.per_family:
                break
            if ex["kind"] in seen_kinds or ex["method"] in seen_methods:
                continue
            seen_kinds.add(ex["kind"])
            seen_methods.add(ex["method"])
            gallery.append(ex)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(gallery, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(
        f"wrote {args.out}: {len(gallery)} examples from {sum(len(v) for v in candidates.values())} candidates"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
