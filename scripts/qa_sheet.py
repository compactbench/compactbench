"""A human QA sheet for a suite's questions: is each one answerable and unambiguous?

    uv run python scripts/qa_sheet.py --suite-pack ../compactbench-hidden/packs/elite_s1/pack.py \
        --suite elite --per-family 8 --focus buried_constraint/constraint_application/violations \
        --out .local/qa/s1-item-review.html

Generates a fresh sample (seed group ``--seed-group``), picks ``--per-family`` items per
family — every question template at least once, ``--focus`` templates oversampled — and
writes one self-contained HTML page: the question, the options with the expected answer
marked, superseded values and traps, and the transcript turns that contain the answer.
Reviewers mark each item OK / ambiguous / wrong answer / unanswerable; marks are kept in
the browser and exported as CSV. For a hidden suite the page shows hidden content: keep
it in ``.local/`` and share it only with reviewers under the same confidentiality.
"""

from __future__ import annotations

import argparse
import html
import json
import random
import re
import sys
from collections import defaultdict
from pathlib import Path

from compactbench.contracts import GeneratedCase, Probe, Turn
from compactbench.scenarios.generate import expand_suite, get_suite, load_suite_pack


def template(probe: Probe) -> str:
    family, _, rest = probe.key.partition("/")
    return f"{family}/{probe.category.value}/{rest.split('_', 1)[0]}"


def evidence(
    case: GeneratedCase, probe: Probe, asked_at: int, limit: int = 4
) -> list[tuple[int, Turn, str]]:
    """Turns up to the cycle the probe is asked at that mention an expected answer, newest first."""
    needles = [a for a in probe.answer if a and a.lower() not in ("not stated", "none")]
    if not needles:
        return []
    found: list[tuple[int, Turn, str]] = []
    for spec in case.cycles[: asked_at + 1]:
        for turn in spec.turns:
            low = turn.content.lower()
            hits = [n for n in needles if n.lower() in low]
            if hits:
                found.append((spec.cycle, turn, hits[0]))
    return list(reversed(found))[:limit]


def excerpt(text: str, needle: str, width: int = 360) -> str:
    """HTML-escaped window of ``text`` around ``needle``, with the needle highlighted."""
    i = text.lower().find(needle.lower())
    start, end = max(0, i - width), min(len(text), i + len(needle) + width)
    before, hit, after = text[start:i], text[i : i + len(needle)], text[i + len(needle) : end]
    return (
        ("…" if start else "")
        + html.escape(before)
        + f"<mark>{html.escape(hit)}</mark>"
        + html.escape(after)
        + ("…" if end < len(text) else "")
    )


def pick_items(
    cases: list[GeneratedCase], per_family: int, focus: set[str], rng: random.Random
) -> list[tuple[GeneratedCase, int, Probe]]:
    """Per family: one item per template, then the focus templates, then random fill."""
    pool: dict[str, dict[str, list[tuple[GeneratedCase, int, Probe]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for case in cases:
        last: dict[str, tuple[int, Probe]] = {}
        for spec in case.cycles:
            for probe in spec.probes:
                last[probe.key] = (spec.cycle, probe)  # review each probe where it's last asked
        for cycle, probe in last.values():
            family = probe.family or case.family
            pool[family][template(probe)].append((case, cycle, probe))
    chosen: list[tuple[GeneratedCase, int, Probe]] = []
    for family in sorted(pool):
        templates = pool[family]
        picks: list[tuple[GeneratedCase, int, Probe]] = []
        for t in sorted(templates):
            rng.shuffle(templates[t])
            picks.append(templates[t].pop())
        for t in sorted(templates):
            if t in focus:
                picks += [templates[t].pop() for _ in range(min(3, len(templates[t])))]
        rest = [x for t in sorted(templates) for x in templates[t]]
        rng.shuffle(rest)
        picks += rest[: max(0, per_family - len(picks))]
        chosen += picks
    return chosen


PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Item review</title>
<style>
:root{--bg:#05060b;--card:#0b0e17;--line:#1a2133;--text:#e6eaf2;--muted:#8a93a6;--ok:#34d399;--bad:#f87171;--accent:#22d3ee}
body{margin:0;background:var(--bg);color:var(--text);font:15px/1.55 system-ui,sans-serif}
main{max-width:980px;margin:0 auto;padding:24px 16px 80px}h1{font-size:1.4rem}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px;margin:16px 0}
.meta{color:var(--muted);font:12px ui-monospace,monospace}.q{font-weight:600;margin:8px 0}
ul{margin:6px 0}li.right{color:var(--ok)}li.right::after{content:"  ✓ expected"}
.ev{background:#070910;border-left:3px solid var(--line);padding:8px 10px;margin:6px 0;font-size:13px;white-space:pre-wrap}
mark{background:#1d4ed8;color:#fff;border-radius:3px;padding:0 2px}.muted{color:var(--muted)}
.review{display:flex;gap:12px;flex-wrap:wrap;align-items:center;margin-top:10px}
textarea{width:100%;background:#070910;color:var(--text);border:1px solid var(--line);border-radius:6px;min-height:38px}
.bar{position:sticky;top:0;background:var(--bg);padding:10px 0;border-bottom:1px solid var(--line);display:flex;gap:12px;align-items:center}
button{background:var(--accent);color:#000;border:0;border-radius:6px;padding:6px 12px;font-weight:600;cursor:pointer}
</style></head><body><main>
<h1>Item review — __TITLE__</h1>
<p class="muted">For each item: could a careful reader with the full conversation give exactly the expected
answer, and only that? Mark it, add a note for anything not OK. Marks stay in this browser; export when done.
Evidence shows turns that contain the expected answer (newest first) — the answer may also depend on turns
that don't contain it, so check the conversation context the question implies.</p>
<div class="bar"><span id="progress"></span><button id="export">Export CSV</button></div>
__ITEMS__
</main><script>
const KEY="cb-review-__STAMP__";
let marks={};try{marks=JSON.parse(localStorage.getItem(KEY)||"{}")}catch{}
const save=()=>{try{localStorage.setItem(KEY,JSON.stringify(marks))}catch{}};
const progress=()=>{const n=Object.values(marks).filter(m=>m.verdict).length;
document.getElementById("progress").textContent=`${n} / ${document.querySelectorAll(".card").length} reviewed`};
for(const card of document.querySelectorAll(".card")){const id=card.dataset.id;const m=marks[id]||{};
for(const r of card.querySelectorAll("input[type=radio]")){r.checked=m.verdict===r.value;
r.addEventListener("change",()=>{marks[id]={...(marks[id]||{}),verdict:r.value};save();progress()})}
const t=card.querySelector("textarea");t.value=m.note||"";
t.addEventListener("input",()=>{marks[id]={...(marks[id]||{}),note:t.value};save()})}
progress();
document.getElementById("export").addEventListener("click",()=>{
const q=s=>'"'+String(s??"").replace(/"/g,'""')+'"';
const rows=[["id","template","verdict","note"],...[...document.querySelectorAll(".card")].map(c=>
[c.dataset.id,c.dataset.template,(marks[c.dataset.id]||{}).verdict,(marks[c.dataset.id]||{}).note])];
const blob=new Blob([rows.map(r=>r.map(q).join(",")).join("\\n")],{type:"text/csv"});
const a=document.createElement("a");a.href=URL.createObjectURL(blob);a.download="item-review.csv";a.click()});
</script></body></html>"""


def render_item(n: int, case: GeneratedCase, cycle: int, probe: Probe) -> str:
    item_id = f"{case.case_id}:{probe.key}"
    expected = set(probe.answer)
    if probe.options:
        body = (
            "<ul>"
            + "".join(
                f'<li class="{"right" if o in expected else ""}">{html.escape(o)}</li>'
                for o in probe.options
            )
            + "</ul>"
        )
    else:
        body = f"<p>Expected: <strong>{html.escape(' | '.join(probe.answer) or '(none)')}</strong> ({probe.value_kind.value})</p>"
    extras = ""
    if probe.stale:
        extras += f"<p class='muted'>Superseded (a stale answer): {html.escape(' | '.join(probe.stale))}</p>"
    if probe.traps:
        extras += f"<p class='muted'>Traps (decoys): {html.escape(' | '.join(probe.traps))}</p>"
    ev = evidence(case, probe, cycle)
    ev_html = (
        "".join(
            f"<div class='ev'><span class='meta'>cycle {c} · turn {t.id} · {t.role.value}</span>\n{excerpt(t.content, hit)}</div>"
            for c, t, hit in ev
        )
        or "<p class='muted'>No turn contains the expected answer verbatim (expected for abstention and set questions).</p>"
    )
    radios = "".join(
        f"<label><input type='radio' name='v{n}' value='{v}'> {label}</label>"
        for v, label in (
            ("ok", "OK"),
            ("ambiguous", "Ambiguous"),
            ("wrong", "Wrong answer"),
            ("unanswerable", "Unanswerable"),
        )
    )
    return (
        f"<section class='card' data-id='{html.escape(item_id)}' data-template='{html.escape(template(probe))}'>"
        f"<div class='meta'>#{n} · {html.escape(template(probe))} · asked after compaction {cycle + 1} · "
        f"{probe.format.value} · {html.escape(case.setting)}</div>"
        f"<p class='q'>{html.escape(probe.question)}</p>{body}{extras}"
        f"<details><summary>Evidence ({len(ev)})</summary>{ev_html}</details>"
        f"<div class='review'>{radios}</div><textarea placeholder='Note'></textarea></section>"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite-pack", type=Path)
    parser.add_argument("--suite", default="practice")
    parser.add_argument("--seed-group", default="qa-review")
    parser.add_argument("--cases", type=int, default=8)
    parser.add_argument("--per-family", type=int, default=8)
    parser.add_argument("--focus", action="append", default=[], help="Template to oversample.")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--out", type=Path, default=Path(".local/qa/item-review.html"))
    args = parser.parse_args()

    if args.suite_pack:
        load_suite_pack(args.suite_pack)
    suite = get_suite(args.suite)
    cases = expand_suite(suite, seed_group=args.seed_group, cases_per_family=args.cases)
    items = pick_items(cases, args.per_family, set(args.focus), random.Random(args.seed))
    body = "\n".join(
        render_item(n, case, cycle, probe) for n, (case, cycle, probe) in enumerate(items, 1)
    )
    stamp = re.sub(r"[^a-z0-9]+", "-", f"{suite.label}-{args.seed_group}".lower())
    page = (
        PAGE.replace("__TITLE__", html.escape(f"{suite.label} · {len(items)} items"))
        .replace("__STAMP__", stamp)
        .replace("__ITEMS__", body)
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(page, encoding="utf-8")
    counts: dict[str, int] = defaultdict(int)
    for _, _, probe in items:
        counts[probe.family or "?"] += 1
    print(f"wrote {args.out}: {len(items)} items " + json.dumps(counts))
    return 0


if __name__ == "__main__":
    sys.exit(main())
