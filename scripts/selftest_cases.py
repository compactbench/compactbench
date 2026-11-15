"""Build the MCP self-test data: public cases an AI can compact and be scored on.

Writes ``web/src/generated/selftest.json``: a few Starter cases (short, one failure family
each) and Practice cases (full size, every family mixed), with each cycle's turns as the
compaction methods see them and its multiple-choice questions. The answer key is in the
same file but the Worker only uses it to score; the tools never send it before scoring.

Everything comes from the public suites with a fixed seed group, so anyone can regenerate
it. Value questions (exact figures typed by the reader) are left out for now: choice
questions score mechanically from letters alone.

    python scripts/selftest_cases.py
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from compactbench.contracts.case import NOT_STATED, ProbeFormat
from compactbench.rendering import render_turns
from compactbench.scenarios import expand_suite, get_suite
from compactbench.scoring import option_letter

OUT = Path("web/src/generated/selftest.json")
SEED_GROUP = "selftest"
BUDGET_TOKENS = 1024
FULL_CASES = 2


def _letters(options: list[str], picks: list[str]) -> list[str]:
    return sorted(option_letter(options.index(p)) for p in picks if p in options)


def _case(case: Any, case_id: str, size: str) -> tuple[dict[str, Any], dict[str, Any]]:
    cycles: list[dict[str, Any]] = []
    keys: dict[str, Any] = {}
    for spec in case.cycles:
        questions: list[dict[str, Any]] = []
        for probe in spec.probes:
            if probe.format not in (ProbeFormat.SINGLE, ProbeFormat.MULTI):
                continue
            qid = f"c{spec.cycle}-q{len(questions) + 1}"
            family = probe.family or case.family
            questions.append(
                {
                    "id": qid,
                    "family": family,
                    "format": probe.format.value,
                    "question": probe.question,
                    "options": [
                        f"{option_letter(i)}. {text}" for i, text in enumerate(probe.options)
                    ],
                }
            )
            keys[qid] = {
                "cycle": spec.cycle,
                "family": family,
                "format": probe.format.value,
                "answer": _letters(probe.options, probe.answer),
                "stale": _letters(probe.options, probe.stale),
                "traps": _letters(probe.options, probe.traps),
                "abstain": probe.answer in ([NOT_STATED], []),
            }
        cycles.append(
            {"cycle": spec.cycle, "turns": render_turns(spec.turns), "questions": questions}
        )
    public = {
        "id": case_id,
        "size": size,
        "suite": f"{case.suite}@{get_suite(case.suite).version}",
        "family": case.family,
        "difficulty": case.difficulty,
        "cycles": cycles,
    }
    return public, keys


def main() -> int:
    cases: list[dict[str, Any]] = []
    keys: dict[str, Any] = {}
    for case in expand_suite(get_suite("starter"), seed_group=SEED_GROUP, cases_per_family=1):
        public, key = _case(case, f"quick-{case.family.replace('_', '-')}", "quick")
        if not key:  # a family that only asks for typed values has nothing to score yet
            continue
        cases.append(public)
        keys[public["id"]] = key
    practice = expand_suite(
        get_suite("practice"), seed_group=SEED_GROUP, cases_per_family=FULL_CASES
    )
    for i, case in enumerate(practice, 1):
        public, key = _case(case, f"full-{i}", "full")
        cases.append(public)
        keys[public["id"]] = key
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(
            {
                "seed_group": SEED_GROUP,
                "budget_tokens": BUDGET_TOKENS,
                "cases": cases,
                "keys": keys,
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    questions = sum(len(c["questions"]) for case in cases for c in case["cycles"])
    print(f"wrote {OUT}: {len(cases)} cases, {questions} questions, {OUT.stat().st_size:,} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
