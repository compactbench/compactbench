"""Turn a finished evaluation into a published submission directory.

    python scripts/ranked/publish.py <evaluation-dir> <repo-root> --season seasons/s1.yaml

Reads the evaluation artifact as data — the results must parse as a CompactBench run
and qualify for the season (if not, the reasons go to ``rejection.txt`` for the status
page) — and writes ``submissions/<handle>/<method>/`` with the method's source (the
public audit trail), its public submission fields, the results (scores only) and the
commitment to the private traces. Prints the score.

A resubmission of the same method replaces the previous files; git history keeps them.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from compactbench.leaderboard import load_season, qualify
from compactbench.runner import to_run_result
from compactbench.submission import SubmissionBundle


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("evaluation", type=Path)
    parser.add_argument("repo", type=Path)
    parser.add_argument("--season", type=Path, required=True)
    args = parser.parse_args()

    bundle = SubmissionBundle.model_validate_json(
        (args.evaluation / "bundle.json").read_text(encoding="utf-8")
    )
    run = to_run_result(args.evaluation / "results.jsonl")
    outcome = qualify(run, season=load_season(args.season))
    if not outcome.qualified:
        reasons = "; ".join(outcome.reasons)
        print(f"::error::run doesn't qualify: {reasons}")
        # For the submitter's status page (harness-written text only).
        (args.evaluation / "rejection.txt").write_text(reasons, encoding="utf-8")
        return 1
    if run.method_name != bundle.method_name or run.method_version != bundle.method_version:
        print("::error::the run's method name or version doesn't match the submission")
        return 1

    target = args.repo / "submissions" / bundle.handle / bundle.method_name
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    (target / "method.py").write_text(bundle.method_py, encoding="utf-8")
    if bundle.requirements.strip():
        (target / "requirements.txt").write_text(bundle.requirements, encoding="utf-8")
    (target / "submission.json").write_text(
        json.dumps(bundle.public(), indent=2) + "\n", encoding="utf-8"
    )
    shutil.copyfile(args.evaluation / "results.jsonl", target / "results.jsonl")
    shutil.copyfile(args.evaluation / "commitment.json", target / "commitment.json")
    print(f"{run.metrics.score:.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
