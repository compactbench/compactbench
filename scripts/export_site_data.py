"""Export what the website shows from the package and docs, so there's one source of truth.

    uv run python scripts/export_site_data.py [web/src/generated]

Writes ``families.json``, ``suites.json``, ``season.json`` and ``leaderboard.json``,
plus the methodology, submission, privacy and submission-terms pages converted
from ``docs/`` (MkDocs admonitions become blockquotes; diagrams are dropped).
The website build runs this first.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

from compactbench.leaderboard import load_season
from compactbench.scenarios import PROFILES, PUBLIC_FAMILIES, SUITES, get_family

ROOT = Path(__file__).resolve().parents[1]
_ADMONITION = re.compile(r'^!!! \w+ "([^"]+)"\n((?:    .*\n?)+)', re.MULTILINE)
_MERMAID = re.compile(r"^```mermaid\n.*?^```\n", re.MULTILINE | re.DOTALL)
PAGES = ("methodology", "submitting", "privacy", "submission-terms", "datasheet")
#: Developer docs served under /docs/<slug>: slug -> (source under docs/, description).
DOCS = {
    "getting-started": (
        "getting-started.md",
        "Install CompactBench, run a built-in method on the Practice suite and read the results.",
    ),
    "writing-a-compactor": (
        "writing-a-compactor.md",
        "Write your own compaction method: one class, one async method, any model.",
    ),
    "forget-less": (
        "forget-less.md",
        "What Season 1 says about compaction instructions, as copy-paste prompts for Claude Code, Codex, LangChain and LlamaIndex.",
    ),
    "ci": (
        "ci.md",
        "Fail a pull request when your agent starts forgetting more: compactbench check and the GitHub Action.",
    ),
    "integrations": (
        "integrations.md",
        "Benchmark the LangChain or LlamaIndex compaction you already have, with thin adapters.",
    ),
    "elite-program": (
        "elite-program.md",
        "The ranked Elite track: tiers, what stays hidden, and how seasons keep it fair.",
    ),
    "elite-versions": (
        "governance/elite-versions.md",
        "How families, suites and seasons are versioned, retired and reviewed.",
    ),
    "faq": ("faq.md", "Common questions about what CompactBench measures and how to use it."),
    "related-work": (
        "related-work.md",
        "Other benchmarks for compaction, memory and long context, and where each one fits.",
    ),
}
_REPO_DOCS = "https://github.com/compactbench/compactbench/blob/main/docs/"


def _route(target: str) -> str:
    """Where a link to ``docs/<target>.md`` lives on the site."""
    name = target.removesuffix(".md").split("/")[-1]
    if name in PAGES or name == "leaderboard":
        return f"/{name}"
    if name == "index":
        return "/"
    if name in DOCS:
        return f"/docs/{name}"
    return _REPO_DOCS + target


def _markdown(path: Path) -> str:
    text = path.read_text(encoding="utf-8")

    def quote(match: re.Match[str]) -> str:
        body = " ".join(line.strip() for line in match.group(2).splitlines() if line.strip())
        return f"> **{match.group(1)}.** {body}\n"

    text = _ADMONITION.sub(quote, text)
    text = _MERMAID.sub("", text)
    # Links to the published data: the leaderboard is served by the site, the rest from the repo.
    text = re.sub(
        r"\]\(data/([a-z-]+\.json)\)",
        lambda m: (
            f"](/api/{m.group(1)})"
            if m.group(1) == "leaderboard.json"
            else f"]({_REPO_DOCS}data/{m.group(1)})"
        ),
        text,
    )
    # Links between docs pages become site routes (anchors kept).
    return re.sub(
        r"\]\(((?:\.\./)?(?:[a-z-]+/)?[a-z-]+\.md)(#[a-z0-9-]+)?\)",
        lambda m: f"]({_route(m.group(1).removeprefix('../'))}{m.group(2) or ''})",
        text,
    )


def slug_of(row: dict[str, object]) -> str:
    """URL slug for a leaderboard row: submitter, method, version, model and season, so
    reruns and two submitters' same-named methods don't collide. The site uses it as is."""
    parts = [row.get("handle"), row["method_name"], row["method_version"], row["compactor_model"]]
    parts.append(row.get("season") or "adhoc")
    text = "-".join(str(p) for p in parts if p).lower()
    return re.sub(r"[^a-z0-9.]+", "-", text).strip("-")


def _fingerprint(row: dict[str, object]) -> str:
    fields = ("handle", "method_name", "method_version", "compactor_provider", "compactor_model")
    fields += ("model_label", "season", "reference_method")
    text = "\x00".join(str(row.get(f) or "") for f in fields)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]


def assign_slugs(rows: list[dict[str, object]]) -> None:
    """Give every row a unique ``slug``.

    Hyphens in handles and method names look like the separators, so two different rows
    can share :func:`slug_of` (``alice`` + ``smart-ledger`` and ``alice-smart`` +
    ``ledger``). The row published first keeps the plain slug, so existing links and
    badges keep working; a later one gets a short fingerprint of what makes it different.
    """
    groups: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        groups.setdefault(slug_of(row), []).append(row)
    for slug, group in groups.items():
        group.sort(key=lambda r: (str(r.get("published_at") or ""), _fingerprint(r)))
        for i, row in enumerate(group):
            row["slug"] = slug if i == 0 else f"{slug}-{_fingerprint(row)}"
    slugs = [row["slug"] for row in rows]
    if len(set(slugs)) != len(slugs):
        raise SystemExit("two leaderboard rows have the same page slug")


def _method_images(rows: list[dict[str, object]]) -> None:
    """A share image per method, into web/public/og/methods/ (needs web/node_modules)."""
    sys.path.insert(0, str(Path(__file__).parent))
    import og_images

    if not og_images.fonts_available():
        print("skipped method images: run `npm ci` in web/ first")
        return
    target = ROOT / "web" / "public" / "og" / "methods"
    if target.exists():
        shutil.rmtree(target)
    for row in rows:
        og_images.method_image(row, target / f"{row['slug']}.png")


def main(argv: list[str]) -> int:
    out = Path(argv[1]) if len(argv) > 1 else ROOT / "web" / "src" / "generated"
    out.mkdir(parents=True, exist_ok=True)

    families = [
        {
            "key": key,
            "title": get_family(key).title,
            "version": get_family(key).version,
            "description": get_family(key).description,
        }
        for key in PUBLIC_FAMILIES
    ]
    suites = [
        {
            "key": suite.key,
            "version": suite.version,
            "description": suite.description,
            "difficulty": suite.difficulty.value,
            "families": list(suite.families),
            "cases": suite.cases_per_family,
            "opening_tokens": PROFILES[suite.difficulty].initial_tokens,
            "drift_cycles": PROFILES[suite.difficulty].drift_cycles,
        }
        for suite in SUITES.values()
    ]
    season = load_season(ROOT / "seasons" / "s1.yaml")
    (out / "families.json").write_text(json.dumps(families, indent=2), encoding="utf-8")
    (out / "suites.json").write_text(json.dumps(suites, indent=2), encoding="utf-8")
    (out / "season.json").write_text(
        json.dumps(season.model_dump(mode="json", exclude={"public_key"}), indent=2),
        encoding="utf-8",
    )
    board = json.loads((ROOT / "docs" / "data" / "leaderboard.json").read_text(encoding="utf-8"))
    assign_slugs(board.get("entries", []))
    (out / "leaderboard.json").write_text(json.dumps(board, indent=2), encoding="utf-8")
    _method_images(board.get("entries", []))
    gallery = ROOT / "docs" / "data" / "failure-gallery.json"
    (out / "failure-gallery.json").write_text(
        gallery.read_text(encoding="utf-8") if gallery.exists() else "[]", encoding="utf-8"
    )
    calibration = ROOT / "seasons" / f"{season.key}.calibration.json"
    (out / "calibration.json").write_text(
        calibration.read_text(encoding="utf-8") if calibration.exists() else "null",
        encoding="utf-8",
    )
    for name in PAGES:
        (out / f"{name}.md").write_text(_markdown(ROOT / "docs" / f"{name}.md"), encoding="utf-8")
    docs_out = out / "docs"
    docs_out.mkdir(exist_ok=True)
    index = []
    for slug, (source, description) in DOCS.items():
        text = _markdown(ROOT / "docs" / source)
        (docs_out / f"{slug}.md").write_text(text, encoding="utf-8")
        title = next((ln[2:].strip() for ln in text.splitlines() if ln.startswith("# ")), slug)
        index.append({"slug": slug, "title": title, "description": description})
    (out / "docs.json").write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
    print(f"wrote site data to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
