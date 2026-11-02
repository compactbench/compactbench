"""Turn a season's calibration run into the ceiling and floor the Seasons page shows.

    uv run python scripts/season_calibration.py .local/calibration/s1-calibration.jsonl \
        seasons/s1.calibration.json

The calibration run is any run with ``--controls`` on the season's settings. Only
aggregates are written — per family, the score a fixed reader gets from the full
conversation (ceiling) and from nothing (floor) — never cases or questions.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from compactbench.runner import to_run_result


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("usage: season_calibration.py <calibration.jsonl> <out.json>", file=sys.stderr)
        return 2
    run = to_run_result(Path(argv[1]))
    families = run.metrics.by_family
    if any(f.oracle_score is None or f.null_score is None for f in families.values()):
        print("the calibration run needs --controls", file=sys.stderr)
        return 1
    out = {
        # A calibration run isn't itself a season run; the file name says which season.
        "season": run.season or Path(argv[2]).name.split(".")[0],
        "suite": f"{run.suite}@{run.suite_version}",
        "reader": f"{run.reader_model} (effort {run.reader_effort or 'default'})",
        "cases": len(run.cases),
        "measured_at": run.completed_at.date().isoformat(),
        "families": {
            key: {
                "ceiling": round(fm.oracle_score or 0.0, 3),
                "floor": round(fm.null_score or 0.0, 3),
            }
            for key, fm in sorted(families.items())
        },
    }
    Path(argv[2]).write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
