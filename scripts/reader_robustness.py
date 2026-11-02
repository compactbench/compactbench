"""Reader robustness: does a second reader, from another model family, rank methods the same?

    uv run python scripts/reader_robustness.py --traces-dir .local/traces/s1-claude-haiku-5-5 \
        --reader-provider groq --reader-model openai/gpt-oss-120b \
        [--cases 3] [--cycles 4] [--tokens-per-minute 7000] [--estimate]

For a fixed subsample of each method's traced cases, the second reader is asked the same
questions about exactly the context the season reader saw (the trace's
``visible_context``), and both readers' answers are scored the same way. Only the reader
differs, so any change in the method ordering is the reader's doing. Reports each
method's score under both readers, per-probe agreement and Kendall's tau-b between the
two orderings; the launch gate is tau >= 0.8.

Traces hold hidden cases: run this locally, keep the output in ``.local/``, and only
use a second-reader key whose provider you're comfortable sending them to. The defaults
fit a free tier (Groq: ~8k tokens a minute, ~200k a day).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from compactbench.config import load_dotenv
from compactbench.contracts import Probe
from compactbench.providers import Provider, get_provider_cls
from compactbench.runner.reader import DEFAULT_CHUNK_SIZE, context_prefix, questions_prompt, read
from compactbench.scoring.answers import counted, score_probe
from compactbench.tokens import count_tokens


@dataclass
class Item:
    method: str
    case_id: str
    cycle: int
    context: str
    probes: list[Probe]
    first_scores: dict[str, float]
    """The season reader's score per probe key, from the trace."""
    second_scores: dict[str, float] = field(default_factory=dict[str, float])


def load_items(traces_dir: Path, cases: int, cycles: set[int]) -> list[Item]:
    """The same case positions for every method: the first ``cases`` case ids, sorted."""
    items: list[Item] = []
    for path in sorted(traces_dir.glob("*.traces.jsonl")):
        method = path.name.removesuffix(".traces.jsonl")
        records: dict[str, list[dict[str, Any]]] = defaultdict(list)
        with path.open(encoding="utf-8") as fp:
            for line in fp:
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue  # a line still being written by a running run
                records[record["case_id"]].append(record)
        for case_id in sorted(records)[:cases]:
            for record in records[case_id]:
                if record["cycle"] not in cycles:
                    continue
                results = record["result"]["probe_results"]
                items.append(
                    Item(
                        method=method,
                        case_id=case_id,
                        cycle=record["cycle"],
                        context=record["visible_context"],
                        probes=[Probe.model_validate(p) for p in record["probes"]],
                        first_scores={r["key"]: r["score"] for r in results},
                    )
                )
    return items


def estimated_tokens(item: Item) -> int:
    """Input tokens for one item's reader calls (output is small next to it)."""
    prefix = count_tokens(context_prefix(item.context))
    total = 0
    for start in range(0, len(item.probes), DEFAULT_CHUNK_SIZE):
        batch = item.probes[start : start + DEFAULT_CHUNK_SIZE]
        total += prefix + count_tokens(
            questions_prompt([(f"Q{i + 1}", p) for i, p in enumerate(batch)])
        )
    return total + 300 * -(-len(item.probes) // DEFAULT_CHUNK_SIZE)


async def rescore(
    items: list[Item],
    provider: Provider,
    model: str,
    tokens_per_minute: int,
    cache: Path | None = None,
) -> None:
    """Ask every item with the second reader, one at a time, pacing to the token rate.

    With ``cache``, each finished item is appended to it as it completes and items already
    in it are skipped, so a run stopped by a daily quota resumes where it left off.
    """
    done: dict[str, dict[str, float]] = {}
    if cache is not None and cache.exists():
        for line in cache.read_text(encoding="utf-8").splitlines():
            if line.strip():
                record = json.loads(line)
                done[record["id"]] = record["scores"]
    for n, item in enumerate(items, 1):
        item_id = f"{item.method}|{item.case_id}|{item.cycle}"
        if item_id in done:
            item.second_scores = done[item_id]
            continue
        started = time.monotonic()
        outcome = await read(provider, model, item.context, item.probes)
        item.second_scores = {
            p.key: score_probe(p, outcome.answers.get(p.key)).score for p in item.probes
        }
        if cache is not None:
            with cache.open("a", encoding="utf-8") as fp:
                fp.write(json.dumps({"id": item_id, "scores": item.second_scores}) + "\n")
        print(
            f"  {n}/{len(items)} {item.method} {item.case_id[-8:]} cycle {item.cycle}", flush=True
        )
        wait = estimated_tokens(item) / max(1, tokens_per_minute) * 60 - (
            time.monotonic() - started
        )
        if wait > 0 and n < len(items):
            await asyncio.sleep(wait)


def method_scores(items: list[Item], which: str) -> dict[str, float]:
    """Mean counted score per method under one reader (same probes for both readers)."""
    by_method: dict[str, list[float]] = defaultdict(list)
    for item in items:
        scores = item.first_scores if which == "first" else item.second_scores
        results = [
            score_probe(p, None).model_copy(update={"score": scores[p.key]})
            for p in item.probes
            if p.key in scores
        ]
        by_method[item.method].extend(counted(results))
    return {m: sum(v) / len(v) for m, v in by_method.items() if v}


def kendall_tau_b(a: dict[str, float], b: dict[str, float]) -> float:
    """Kendall's tau-b between two scorings of the same methods (ties handled)."""
    keys = sorted(set(a) & set(b))
    concordant = discordant = ties_a = ties_b = 0
    for i, x in enumerate(keys):
        for y in keys[i + 1 :]:
            da, db = a[x] - a[y], b[x] - b[y]
            if da == 0 and db == 0:
                continue
            if da == 0:
                ties_a += 1
            elif db == 0:
                ties_b += 1
            elif (da > 0) == (db > 0):
                concordant += 1
            else:
                discordant += 1
    denominator = ((concordant + discordant + ties_a) * (concordant + discordant + ties_b)) ** 0.5
    return (concordant - discordant) / denominator if denominator else 1.0


def report(items: list[Item]) -> dict[str, Any]:
    first, second = method_scores(items, "first"), method_scores(items, "second")
    pairs = [
        (item.first_scores[k], item.second_scores[k])
        for item in items
        for k in item.second_scores
        if k in item.first_scores
    ]
    agree = sum(1 for x, y in pairs if x == y) / len(pairs) if pairs else 0.0
    tau = kendall_tau_b(first, second)
    return {
        "methods": {
            m: {"first": round(first[m], 4), "second": round(second.get(m, 0.0), 4)} for m in first
        },
        "probe_agreement": round(agree, 4),
        "kendall_tau_b": round(tau, 4),
        "passes": tau >= 0.8,
        "items": len(items),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--traces-dir", type=Path, required=True)
    parser.add_argument("--reader-provider", required=True)
    parser.add_argument("--reader-model", required=True)
    parser.add_argument("--cases", type=int, default=3, help="Cases per method.")
    parser.add_argument("--cycles", default="4", help="Comma-separated cycles to re-read.")
    parser.add_argument("--tokens-per-minute", type=int, default=7000)
    parser.add_argument(
        "--out", type=Path, default=Path(".local/calibration/reader-robustness.json")
    )
    parser.add_argument("--estimate", action="store_true")
    args = parser.parse_args()

    load_dotenv()  # COMPACTBENCH_<PROVIDER>_API_KEY from .env, as the CLI does
    cycles = {int(c) for c in args.cycles.split(",") if c.strip()}
    items = load_items(args.traces_dir, args.cases, cycles)
    methods = sorted({i.method for i in items})
    tokens = sum(estimated_tokens(i) for i in items)
    calls = sum(-(-len(i.probes) // DEFAULT_CHUNK_SIZE) for i in items)
    print(
        f"{len(items)} items over {len(methods)} methods: ~{calls} calls, "
        f"~{tokens:,} input tokens, ~{tokens / max(1, args.tokens_per_minute):.0f} min at the pace set"
    )
    if args.estimate or not items:
        return 0

    provider = get_provider_cls(args.reader_provider)()
    cache = args.out.with_suffix(
        f".{args.reader_provider}-{args.reader_model.replace('/', '_')}.cache.jsonl"
    )
    asyncio.run(rescore(items, provider, args.reader_model, args.tokens_per_minute, cache))
    result = report(items) | {"reader": f"{args.reader_provider}/{args.reader_model}"}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if result["passes"] else 1


if __name__ == "__main__":
    sys.exit(main())
