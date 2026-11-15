"""Build the public CompactBench suites as a Hugging Face dataset.

Writes ``<out>/data/<suite>.jsonl`` (one case per line) and ``<out>/README.md`` (the
dataset card) for the public ``starter``, ``practice`` and ``drills`` suites, with the same
cases ``compactbench run --suite <suite>`` uses (seed group ``default``). Nothing from the
hidden ranked set is included: these suites are generated from the open-source package.

    python scripts/hf_dataset.py build/hf

Publishing is a separate, manual step with the maintainers' Hugging Face token, e.g.
``huggingface-cli upload compactbench/compactbench build/hf . --repo-type dataset``.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from compactbench import __version__
from compactbench.runner import SCORER_VERSION
from compactbench.scenarios import expand_suite, get_suite

SUITES = ("practice", "starter", "drills")
#: Largest data file written; bigger suites are split into shards that load as one config.
MAX_SHARD_BYTES = 8_000_000
SEED_GROUP = "default"
REPO_ID = "compactbench/compactbench"
ABOUT = {
    "practice": "Public twin of the ranked set: every family mixed into one long session, "
    "Elite difficulty, ~32k-token openings",
    "starter": "Short cases (~1.5k tokens), one family each, for a first end-to-end try",
    "drills": "One family per case at Elite difficulty, to work on one failure mode",
}


def case_record(case: Any, suite_version: str) -> dict[str, Any]:
    """One dataset row. Seeds are strings: they are unsigned 64-bit integers, which Arrow's
    signed integers can't hold."""
    record = case.model_dump(mode="json")
    record["seed"] = str(case.seed)
    record["suite_version"] = suite_version
    return record


def build(out: Path) -> dict[str, int]:
    (out / "data").mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    stats: dict[str, dict[str, int]] = {}
    for key in SUITES:
        suite = get_suite(key)
        cases = expand_suite(suite, seed_group=SEED_GROUP)
        write_shards(
            out / "data",
            key,
            [json.dumps(case_record(c, suite.version), ensure_ascii=False) + "\n" for c in cases],
        )
        counts[key] = len(cases)
        stats[key] = {
            "cases": len(cases),
            "compactions": len(cases[0].cycles),
            "questions": sum(len(c.probes) for case in cases for c in case.cycles),
        }
    (out / "README.md").write_text(card(stats), encoding="utf-8")
    return counts


def write_shards(folder: Path, key: str, lines: list[str]) -> list[Path]:
    """Write ``lines`` to ``<key>-00000-of-0000N.jsonl`` files of at most MAX_SHARD_BYTES."""
    shards: list[list[str]] = [[]]
    size = 0
    for line in lines:
        n = len(line.encode("utf-8"))
        if shards[-1] and size + n > MAX_SHARD_BYTES:
            shards.append([])
            size = 0
        shards[-1].append(line)
        size += n
    for old in folder.glob(f"{key}-*.jsonl"):
        old.unlink()
    paths: list[Path] = []
    for i, chunk in enumerate(shards):
        path = folder / f"{key}-{i:05d}-of-{len(shards):05d}.jsonl"
        path.write_text("".join(chunk), encoding="utf-8")
        paths.append(path)
    return paths


def card(stats: dict[str, dict[str, int]]) -> str:
    version = get_suite("practice").version
    configs = "\n".join(
        f'  - config_name: {key}\n    data_files: "data/{key}-*.jsonl"'
        + ("\n    default: true" if key == "practice" else "")
        for key in SUITES
    )
    rows = "\n".join(
        f"| `{key}` | {ABOUT[key]} | {s['cases']} | {s['compactions']} | {s['questions']:,} |"
        for key, s in stats.items()
    )
    return f"""---
license: apache-2.0
language:
  - en
pretty_name: CompactBench (public suites)
size_categories:
  - n<1K
task_categories:
  - question-answering
  - summarization
tags:
  - context-compaction
  - long-context
  - agents
  - memory
  - benchmark
  - synthetic
configs:
{configs}
---

# CompactBench: public suites

CompactBench measures how much an AI agent forgets when its context is **compacted**:
rewritten as a short summary so a long session can continue. Each case is a long, multi-turn
working conversation that is compacted several times; after every compaction, questions are
asked that can only be answered from what the compacted memory kept. Rules are stated once
and later narrowed, decisions are overridden and reverted, owners change, figures are
corrected, and look-alike values from other projects and untrusted documents are planted as
traps.

This dataset holds the **public suites** (suite version {version}), exactly the cases
`compactbench run --suite <name>` uses. The ranked leaderboard runs on a separate hidden set
generated the same way in private worlds; nothing from it is included here.

| Config | What it is | Cases | Compactions per case | Questions |
|---|---|---:|---:|---:|
{rows}

Code, method interface, scoring and leaderboard: <https://github.com/compactbench/compactbench>.

## How a case is used

For each cycle in order, a compaction method receives the cycle's `turns` (the first cycle:
the whole opening conversation; later cycles: only the turns since the last compaction, plus
the method's own previous output) and writes a memory within a token budget (Season 1: 1,024
`cl100k_base` tokens). A fixed reader model then answers that cycle's `probes` from the memory
alone, and answers are scored mechanically (no LLM judge). The overall score averages the
failure families so each counts equally.

The easiest way to run it is the package, which does the loop, the reader and the scoring:

```bash
pip install "compactbench[providers] @ git+https://github.com/compactbench/compactbench"
compactbench run --method built-in:sectioned-summary --suite practice \\
    --provider anthropic --model claude-haiku-5-5 --budget 1024
```

To load the raw cases:

```python
from datasets import load_dataset

practice = load_dataset("{REPO_ID}", "practice", split="train")
case = practice[0]
first_turns = case["cycles"][0]["turns"]
first_questions = case["cycles"][0]["probes"]
```

## Fields

- `case_id`, `suite`, `suite_version`, `difficulty`, `setting`, `seed` (string)
- `family`, `family_version`: the failure family, or `mixed` for a session with every family
- `cycles[]`: one entry per compaction
  - `cycle`: 0 for the opening conversation
  - `turns[]`: `id`, `role` (`user`, `assistant`, `system`, `tool`), `content`, `name` (tool
    name), `tags`
  - `probes[]`: the questions asked after this compaction
    - `key` (stable across cycles for a question asked again), `category`, `family`,
      `origin_cycle` (the cycle whose turns introduced the information)
    - `format`: `single` (pick one option), `multi` (select all that apply), `value` (one exact
      value) or `list` (every value in a set); `value_kind` says how values are normalized
      (`text`, `number`, `money`, `date`, `ident`, `version`, `name`)
    - `question`, `options` (for choice formats)
    - `answer`: the correct option texts or values. An answer of "Not stated in the
      conversation" or an empty selection means the information was never settled
    - `stale`: answers that were correct earlier and have since been superseded
    - `traps`: answers supported only by a decoy (another project's rule, a rejected
      proposal, an instruction smuggled in through tool output)

## Failure families

`buried_constraint`, `decision_override`, `entity_confusion`, `reference_resolution`,
`numeric_precision`, `conditional_scope`, `task_continuity` and `provenance_authority`. The
`practice` config mixes all eight into each conversation, like the ranked set; `drills` and
`starter` have one family per case.

## How it was made

Every case is generated deterministically by the open-source generators in the package
(compactbench {__version__}, scorer {SCORER_VERSION}) from the suite label, family, seed
group and slot: same version, same cases, on any platform. The conversations are synthetic
(fictional companies, people and projects) and contain on-topic procedural filler (code,
logs, API responses, notes). No personal data is included.

## Intended use and limitations

- For developing and comparing compaction, summarization and agent-memory methods, and for
  checking an agent's compaction in CI. Ranked results come from the hidden set, so a method
  tuned on these cases can't carry that tuning to the leaderboard.
- English only; synthetic workplace conversations, so results speak to keeping working
  state (rules, decisions, owners, figures, tasks), not to open-ended dialogue.
- Scores depend on the reader model and the token budget; compare methods with both fixed.

## License

Apache 2.0, like the CompactBench code.
"""


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the public suites as a Hugging Face dataset."
    )
    parser.add_argument("out", type=Path, nargs="?", default=Path("build/hf"))
    args = parser.parse_args()
    counts = build(args.out)
    total = sum(p.stat().st_size for p in (args.out / "data").glob("*.jsonl"))
    print(f"wrote {args.out}: {counts} ({total / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
