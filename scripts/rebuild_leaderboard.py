"""Rebuild docs/data/leaderboard.json from every merged submission's results.jsonl.

Invoked by .github/workflows/update-leaderboard.yml. Reads:

- Every ``submissions/*/*/results.jsonl`` (skips ``_template``).
- The sibling ``config.yaml`` for tier + attribution.

For each run it:

1. Parses the event log into a :class:`RunResult`.
2. Runs qualification checks. Rejected runs are omitted with a warning.
3. Projects to a leaderboard row.

Then ranks the rows and writes the canonical leaderboard JSON.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

from compactbench.leaderboard import (
    CompressionTier,
    LeaderboardRow,
    project_row,
    qualify,
    rank_rows,
)
from compactbench.runner import to_run_result

SUBMISSIONS_DIR = Path("submissions")
LEADERBOARD_PATH = Path("docs/data/leaderboard.json")
SCHEMA_VERSION = "1.0.0"

_VALID_TIERS = {"Elite-Light", "Elite-Mid", "Elite-Aggressive"}


def main() -> int:
    rows: list[LeaderboardRow] = []
    warnings: list[str] = []
    yaml = YAML(typ="safe")

    for submission_dir in sorted(SUBMISSIONS_DIR.iterdir()) if SUBMISSIONS_DIR.is_dir() else []:
        if not submission_dir.is_dir() or submission_dir.name.startswith("_"):
            continue
        for method_dir in sorted(submission_dir.iterdir()):
            if not method_dir.is_dir():
                continue
            results_path = method_dir / "results.jsonl"
            config_path = method_dir / "config.yaml"
            if not results_path.exists() or not config_path.exists():
                continue

            try:
                run_result = to_run_result(results_path)
            except Exception as exc:
                warnings.append(f"skipped {method_dir}: could not parse results.jsonl: {exc}")
                continue

            with config_path.open(encoding="utf-8") as fp:
                config_data: Any = yaml.load(fp)  # pyright: ignore[reportUnknownMemberType]

            if not isinstance(config_data, dict):
                warnings.append(f"skipped {method_dir}: config.yaml is not a mapping")
                continue

            runtime_cfg = config_data.get("runtime", {}) if isinstance(config_data, dict) else {}
            attribution = (
                config_data.get("attribution", {}) if isinstance(config_data, dict) else {}
            )
            tier = (
                str(runtime_cfg.get("compression_tier", ""))
                if isinstance(runtime_cfg, dict)
                else ""
            )
            drift_cycles_raw = (
                runtime_cfg.get("drift_cycles", 2) if isinstance(runtime_cfg, dict) else 2
            )
            try:
                drift_cycles = int(drift_cycles_raw)
            except (TypeError, ValueError):
                drift_cycles = 2

            if tier not in _VALID_TIERS:
                warnings.append(
                    f"skipped {method_dir}: invalid compression_tier {tier!r} "
                    f"(expected one of {sorted(_VALID_TIERS)})"
                )
                continue

            qual = qualify(run_result, tier=tier, expected_drift_cycles=drift_cycles)  # pyright: ignore[reportArgumentType]
            if not qual.qualified:
                warnings.append(f"disqualified {method_dir}: {'; '.join(qual.reasons)}")
                continue

            handle = (
                str(attribution.get("handle"))
                if isinstance(attribution, dict) and attribution.get("handle")
                else None
            )
            org = (
                str(attribution.get("org"))
                if isinstance(attribution, dict) and attribution.get("org")
                else None
            )

            rows.append(
                project_row(
                    run_result,
                    tier=tier,  # pyright: ignore[reportArgumentType]
                    handle=handle,
                    org=org,
                    published_at=run_result.completed_at,
                )
            )

    ranked = rank_rows(rows)

    LEADERBOARD_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "updated_at": datetime.now(UTC).isoformat(),
        "entries": ranked,
    }
    LEADERBOARD_PATH.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    for note in warnings:
        print(f"warning: {note}", file=sys.stderr)
    print(f"wrote {LEADERBOARD_PATH} with {len(ranked)} entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


def _ensure_tier(tier: str) -> CompressionTier:
    """Pyright-friendly narrowing helper (unused at runtime)."""
    assert tier in _VALID_TIERS
    return tier  # type: ignore[return-value]
