"""Seal the method image between the build and evaluate jobs.

    python scripts/ranked/image.py seal IMAGE OUT --season seasons/s1.yaml --id ID
    python scripts/ranked/image.py open SEALED IMAGE --season seasons/s1.yaml --id ID

The image carries the submitted method's code, and artifacts of a public repository can
be downloaded by anyone signed in to GitHub. So the build job (which holds no secrets)
seals it to the season's public key before uploading, and the evaluate job opens it with
the season's private key (``COMPACTBENCH_SEASON_PRIVATE_KEY``). The context binds the
sealed image to this season and submission.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

_ID = re.compile(r"^[a-z0-9]{12,32}$")


def image_context(season: str, submission_id: str) -> str:
    return f"image:{season}:{submission_id}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["seal", "open"])
    parser.add_argument("source", type=Path)
    parser.add_argument("target", type=Path)
    parser.add_argument("--season", type=Path, required=True)
    parser.add_argument("--id", required=True)
    args = parser.parse_args(argv)

    from compactbench.leaderboard import load_season
    from compactbench.sealing import SealingError, open_sealed_file, seal_file

    if not _ID.match(args.id):
        print("::error::bad submission id")
        return 1
    season = load_season(args.season)
    context = image_context(season.key, args.id)
    if args.action == "seal":
        if not season.public_key:
            print("::error::the season has no public key")
            return 1
        seal_file(season.public_key, args.source, args.target, context=context)
        return 0
    private_key = os.environ.pop("COMPACTBENCH_SEASON_PRIVATE_KEY", "")
    if not private_key:
        print("::error::the season private key is missing")
        return 1
    try:
        open_sealed_file(private_key, args.source, args.target, context=context)
    except SealingError:
        print("::error::the method image doesn't open for this submission")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
