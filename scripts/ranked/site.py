"""Talk to compactbench.com from the evaluation workflow, authenticated by GitHub OIDC.

    python scripts/ranked/site.py fetch   <submission_id> <out.json>
    python scripts/ranked/site.py status  <submission_id> <status> [message] [--score S]
    python scripts/ranked/site.py archive <submission_id> <evaluation-dir>

The site trusts these calls because the request carries a GitHub Actions OIDC token
minted for this repository's evaluate workflow on main — no shared secret. The job
needs ``permissions: id-token: write``. ``COMPACTBENCH_SITE`` overrides the site URL.
"""

from __future__ import annotations

import os
import re
import sys
import time
from pathlib import Path

import httpx

SITE = os.environ.get("COMPACTBENCH_SITE", "https://compactbench.com")
_ID = re.compile(r"^[a-z0-9]{12,32}$")
# A finished run's files kept in the site's private archive; the site accepts only these.
ARCHIVE_FILES = (
    "results.sealed",
    "traces.sealed",
    "calls.sealed",
    "commitment.json",
    "submission.json",
    "results.jsonl",
)


def _oidc_token() -> str:
    url = os.environ.get("ACTIONS_ID_TOKEN_REQUEST_URL")
    bearer = os.environ.get("ACTIONS_ID_TOKEN_REQUEST_TOKEN")
    if not url or not bearer:
        raise SystemExit("::error::no OIDC token available (the job needs id-token: write)")
    response = httpx.get(
        url, params={"audience": SITE}, headers={"Authorization": f"bearer {bearer}"}, timeout=30
    )
    response.raise_for_status()
    return str(response.json()["value"])


def fetch(submission_id: str, out: Path) -> None:
    response = httpx.get(
        f"{SITE}/api/internal/bundles/{submission_id}",
        headers={"Authorization": f"Bearer {_oidc_token()}"},
        timeout=60,
    )
    response.raise_for_status()
    out.write_text(response.text, encoding="utf-8")


def status(submission_id: str, value: str, message: str | None, score: float | None) -> None:
    body: dict[str, object] = {"status": value}
    if message:
        body["message"] = message[:500]
    if score is not None:
        body["score"] = score
    response = httpx.post(
        f"{SITE}/api/internal/submissions/{submission_id}",
        headers={"Authorization": f"Bearer {_oidc_token()}"},
        json=body,
        timeout=30,
    )
    response.raise_for_status()


def archive(submission_id: str, directory: Path, attempts: int = 3) -> int:
    """Copy a finished run's files to the private archive. Returns how many didn't make it."""
    missed = 0
    for name in ARCHIVE_FILES:
        path = directory / name
        if not path.is_file():
            continue
        problem = ""
        for attempt in range(attempts):
            try:
                response = httpx.put(
                    f"{SITE}/api/internal/archive/{submission_id}/{name}",
                    headers={"Authorization": f"Bearer {_oidc_token()}"},
                    content=path.read_bytes(),
                    timeout=300,
                )
                response.raise_for_status()
                problem = ""
                break
            except httpx.HTTPStatusError as error:
                problem = f"HTTP {error.response.status_code}"
            except httpx.HTTPError as error:
                problem = type(error).__name__
            if attempt + 1 < attempts:
                time.sleep(5 * (attempt + 1))
        if problem:
            # Workflow logs are public: the file name and the error kind only.
            print(f"::warning::{name} wasn't archived ({problem})")
            missed += 1
    return missed


def main(argv: list[str]) -> int:
    if len(argv) < 4 or argv[1] not in {"fetch", "status", "archive"} or not _ID.match(argv[2]):
        print(__doc__, file=sys.stderr)
        return 2
    if argv[1] == "fetch":
        fetch(argv[2], Path(argv[3]))
        return 0
    if argv[1] == "archive":
        return 1 if archive(argv[2], Path(argv[3])) else 0
    rest = argv[4:]
    score: float | None = None
    if "--score" in rest:
        index = rest.index("--score")
        score = float(rest[index + 1])
        del rest[index : index + 2]
    status(argv[2], argv[3], rest[0] if rest else None, score)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
