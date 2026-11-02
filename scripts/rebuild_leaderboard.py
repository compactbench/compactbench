"""Rebuild docs/data/leaderboard.json from merged submissions and maintainer baselines.

Invoked by .github/workflows/update-leaderboard.yml. Reads:

- Every ``submissions/<handle>/<method>/results.jsonl`` (skips ``_template``),
  with the sibling ``submission.json`` the publish job wrote, for attribution. Each run is checked against
  the qualification floors and, when it names a season, against
  ``seasons/<season>.yaml``. Runs that fail are left out with a warning.
- Every ``baselines/<slug>/*.jsonl`` with its ``manifest.yaml``. These publish
  as **reference rows** — visible, never ranked: maintainer baselines show what
  there is to beat, and the controls (``oracle``, ``null``, ``truncate-last-n``)
  bracket the achievable range on the same reader. ``baselines/archive/`` holds
  retired results from older scorers and is not read.

Then ranks the rows and writes the canonical leaderboard JSON.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from ruamel.yaml import YAML

from compactbench.compactors import CONTROL_KEYS
from compactbench.leaderboard import LeaderboardRow, load_season, project_row, qualify, rank_rows
from compactbench.runner import to_run_result

SUBMISSIONS_DIR = Path("submissions")
BASELINES_DIR = Path("baselines")
SEASONS_DIR = Path("seasons")
LEADERBOARD_PATH = Path("docs/data/leaderboard.json")
SCHEMA_VERSION = "2.0.0"


def _load_yaml(path: Path, yaml: YAML) -> dict[str, Any] | None:
    with path.open(encoding="utf-8") as fp:
        data: Any = yaml.load(fp)  # pyright: ignore[reportUnknownMemberType]
    return data if isinstance(data, dict) else None  # pyright: ignore[reportUnknownVariableType]


def _submission_rows(warnings: list[str]) -> list[LeaderboardRow]:
    """Published ranked submissions: ``submissions/<handle>/<method>/`` with the results
    and ``submission.json`` (the bundle's public fields) the publish job wrote."""
    rows: list[LeaderboardRow] = []
    if not SUBMISSIONS_DIR.is_dir():
        return rows
    for handle_dir in sorted(SUBMISSIONS_DIR.iterdir()):
        if not handle_dir.is_dir() or handle_dir.name.startswith("_"):
            continue
        for method_dir in sorted(p for p in handle_dir.iterdir() if p.is_dir()):
            results_path = method_dir / "results.jsonl"
            meta_path = method_dir / "submission.json"
            if not results_path.exists() or not meta_path.exists():
                continue
            try:
                run = to_run_result(results_path)
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except ValueError as exc:
                warnings.append(f"skipped {method_dir}: {exc}")
                continue
            if not isinstance(meta, dict):
                warnings.append(f"skipped {method_dir}: submission.json is not an object")
                continue
            fields = cast("dict[str, object]", meta)
            season = None
            if run.season is not None:
                season_path = SEASONS_DIR / f"{run.season}.yaml"
                if not season_path.is_file():
                    warnings.append(f"skipped {method_dir}: unknown season {run.season!r}")
                    continue
                season = load_season(season_path)
            outcome = qualify(run, season=season)
            if not outcome.qualified:
                warnings.append(f"disqualified {method_dir}: {'; '.join(outcome.reasons)}")
                continue
            handle = fields.get("handle")
            label = fields.get("model_label")
            rows.append(
                project_row(
                    run,
                    handle=str(handle) if handle else None,
                    org=None,
                    published_at=run.completed_at,
                    model_label=str(label) if label else None,
                )
            )
    return rows


def _baseline_rows(warnings: list[str], yaml: YAML) -> list[LeaderboardRow]:
    rows: list[LeaderboardRow] = []
    if not BASELINES_DIR.is_dir():
        return rows
    for profile_dir in sorted(p for p in BASELINES_DIR.iterdir() if p.is_dir()):
        if profile_dir.name == "archive":
            continue
        manifest_path = profile_dir / "manifest.yaml"
        if not manifest_path.is_file():
            warnings.append(f"skipped {profile_dir}: no manifest.yaml")
            continue
        manifest = _load_yaml(manifest_path, yaml) or {}
        publisher = str(manifest.get("published_by") or "compactbench")
        for results_path in sorted(profile_dir.glob("*.jsonl")):
            try:
                run = to_run_result(results_path)
            except ValueError as exc:
                warnings.append(f"skipped {results_path}: {exc}")
                continue
            kind = "control" if run.method_name in CONTROL_KEYS else "baseline"
            rows.append(
                project_row(
                    run,
                    handle=None,
                    org=publisher,
                    published_at=run.completed_at,
                    row_kind=kind,
                )
            )
    return rows


def main() -> int:
    warnings: list[str] = []
    yaml = YAML(typ="safe")
    ranked = rank_rows(_submission_rows(warnings) + _baseline_rows(warnings, yaml))

    LEADERBOARD_PATH.parent.mkdir(parents=True, exist_ok=True)
    # Keep ``updated_at`` when nothing changed, so a no-op rebuild doesn't
    # produce a commit that branch protection rightly rejects.
    previous: dict[str, object] = {}
    if LEADERBOARD_PATH.exists():
        try:
            loaded: object = json.loads(LEADERBOARD_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            loaded = None
        if isinstance(loaded, dict):
            previous = cast("dict[str, object]", loaded)
    previous_updated_at = previous.get("updated_at")
    if previous.get("entries") == ranked and isinstance(previous_updated_at, str):
        updated_at = previous_updated_at
    else:
        updated_at = datetime.now(UTC).isoformat()

    payload = {"schema_version": SCHEMA_VERSION, "updated_at": updated_at, "entries": ranked}
    LEADERBOARD_PATH.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    for note in warnings:
        print(f"warning: {note}", file=sys.stderr)
    print(f"wrote {LEADERBOARD_PATH} with {len(ranked)} entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
