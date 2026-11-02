"""Run the reference baselines for a season and write them where the leaderboard reads them.

    uv run python scripts/run_baselines.py --season seasons/s1.yaml \
        --suite-pack ../compactbench-hidden/packs/elite_s1/pack.py \
        --provider anthropic --model claude-haiku-5-5 --profile s1-claude-haiku-5-5 \
        [--methods naive-summary,extractive] [--estimate]

Each method runs under the season's pinned settings, on its own fresh sample. The raw
results go to ``--raw-dir`` (default ``.local/results``, gitignored); when a method
finishes, a redacted copy (``compactbench.redaction``: no private probe keys, no
method text) lands in ``baselines/<profile>/<method>.jsonl`` with a ``manifest.yaml``.
Traces hold the hidden cases, so they go to ``--traces-dir`` (default
``.local/traces``) and never into the repository. ``--publish-only`` redacts existing
raw results without running anything; ``--estimate`` prints projected cost.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from compactbench.redaction import redact_results

ROOT = Path(__file__).resolve().parents[1]

#: Methods every season publishes, in display order.
ROSTER = (
    "hierarchical-summary",
    "naive-summary",
    "sectioned-summary",
    "structured-state",
    "hybrid-ledger",
    "anthropic-compaction",
    "extractive",
    "truncate-last-n",
)
#: Methods that need a specific compactor provider.
PROVIDER_ONLY = {"anthropic-compaction": "anthropic"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=Path, required=True)
    parser.add_argument("--suite-pack", type=Path, required=True)
    parser.add_argument("--provider", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--profile", required=True, help="Directory name under baselines/.")
    parser.add_argument("--methods", default=",".join(ROSTER))
    parser.add_argument("--traces-dir", type=Path, default=ROOT / ".local" / "traces")
    parser.add_argument("--raw-dir", type=Path, default=ROOT / ".local" / "results")
    parser.add_argument(
        "--publish-only", action="store_true", help="Redact existing raw results; run nothing."
    )
    parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument("--estimate", action="store_true")
    parser.add_argument("--parallel", type=int, default=1, help="Methods to run at the same time.")
    args = parser.parse_args()

    methods = [m.strip() for m in args.methods.split(",") if m.strip()]
    out_dir = ROOT / "baselines" / args.profile
    raw_dir = args.raw_dir / args.profile
    traces_dir = args.traces_dir / args.profile
    if not args.estimate:
        for directory in (out_dir, raw_dir, traces_dir):
            directory.mkdir(parents=True, exist_ok=True)
        _write_manifest(out_dir / "manifest.yaml", args)

    def publish(method: str) -> None:
        raw = raw_dir / f"{method}.jsonl"
        if raw.exists():
            redact_results(raw, out_dir / f"{method}.jsonl")
            print(f"  published {method} (redacted)", flush=True)

    if args.publish_only:
        for method in methods:
            publish(method)
        return 0

    jobs: list[tuple[str, list[str]]] = []
    for method in methods:
        needed = PROVIDER_ONLY.get(method)
        if needed and needed != args.provider:
            print(f"skip {method}: needs --provider {needed}")
            continue
        argv = [
            "compactbench",
            "run",
            "--season",
            str(args.season),
            "--suite-pack",
            str(args.suite_pack),
            "--method",
            f"built-in:{method}",
            "--provider",
            args.provider,
            "--model",
            args.model,
            "--concurrency",
            str(args.concurrency),
            "--output",
            str(raw_dir / f"{method}.jsonl"),
            "--traces",
            str(traces_dir / f"{method}.traces.jsonl"),
        ]
        if args.estimate:
            argv.append("--estimate")
        jobs.append((method, argv))

    failed: list[str] = []
    running: list[tuple[str, subprocess.Popen[bytes]]] = []
    for method, argv in jobs:
        while len(running) >= max(1, args.parallel):
            failed += _reap(running)
        print(f"→ {method}", flush=True)
        log = None if args.estimate else (raw_dir / f"{method}.log").open("wb")
        running.append((method, subprocess.Popen(argv, stdout=log, stderr=log)))
    while running:
        failed += _reap(running)
    if not args.estimate:
        for method, _ in jobs:
            if method not in failed:
                publish(method)
    if failed:
        print(f"failed: {', '.join(failed)} (rerun with --methods; add --resume via the CLI)")
        return 1
    return 0


def _reap(running: list[tuple[str, subprocess.Popen[bytes]]]) -> list[str]:
    """Wait for the oldest job; return its method if it failed."""
    method, process = running.pop(0)
    code = process.wait()
    print(f"✓ {method}" if code == 0 else f"✗ {method} (exit {code})", flush=True)
    return [] if code == 0 else [method]


def _write_manifest(path: Path, args: argparse.Namespace) -> None:
    if path.exists():
        return
    path.write_text(
        "# Reference baselines: built-in methods run by the maintainers under the season's\n"
        "# pinned settings. Shown on the leaderboard, never ranked.\n"
        f"published_by: compactbench\n"
        f"season: {args.season.stem}\n"
        f"compactor_provider: {args.provider}\n"
        f"compactor_model: {args.model}\n"
        f"created: {datetime.now(UTC).date().isoformat()}\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    sys.exit(main())
