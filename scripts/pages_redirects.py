"""Redirect pages for the old docs site (compactbench.github.io/compactbench).

    python scripts/pages_redirects.py site-redirects/

The docs now live on compactbench.com. GitHub Pages can't send HTTP redirects, so each old
page becomes a tiny HTML page that points search engines (canonical link) and people
(meta refresh, plus a plain link) at its new address. The docs workflow deploys these
instead of the MkDocs build.
"""

from __future__ import annotations

import html
import sys
from pathlib import Path

SITE = "https://compactbench.com"
REPO_DOCS = "https://github.com/compactbench/compactbench/blob/main/docs/"

#: Old MkDocs path (directory URL) -> new address.
MOVED = {
    "": "/",
    "getting-started": "/docs/getting-started",
    "writing-a-compactor": "/docs/writing-a-compactor",
    "integrations": "/docs/integrations",
    "elite-program": "/docs/elite-program",
    "faq": "/docs/faq",
    "related-work": "/docs/related-work",
    "governance/elite-versions": "/docs/elite-versions",
    "ci": "/docs/ci",
    "forget-less": "/docs/forget-less",
    "submitting": "/submit",
    "submission-terms": "/submission-terms",
    "leaderboard": "/leaderboard",
    "methodology": "/methodology",
    "datasheet": "/datasheet",
    "privacy": "/privacy",
    "architecture/decisions": REPO_DOCS + "architecture/decisions.md",
}


def page(target: str) -> str:
    url = html.escape(target if target.startswith("https://") else SITE + target)
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        f'<title>Moved to compactbench.com</title><link rel="canonical" href="{url}">'
        f'<meta http-equiv="refresh" content="0; url={url}"><meta name="robots" content="noindex">'
        f'</head><body><p>CompactBench\'s docs moved to <a href="{url}">{url}</a>.</p></body></html>\n'
    )


def main(argv: list[str]) -> int:
    out = Path(argv[1]) if len(argv) > 1 else Path("site-redirects")
    for old, new in MOVED.items():
        target = out / old / "index.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(page(new), encoding="utf-8")
    (out / "404.html").write_text(page("/"), encoding="utf-8")
    print(f"wrote {len(MOVED) + 1} redirect pages to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
