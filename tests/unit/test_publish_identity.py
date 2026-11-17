"""Published rows keep their own pages and directories, whoever else picks a similar name."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]


def _load(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


export = _load(ROOT / "scripts" / "export_site_data.py", "export_site_data")
publish = _load(ROOT / "scripts" / "ranked" / "publish.py", "ranked_publish")


def _row(handle: str, method: str, published: str, **extra: object) -> dict[str, object]:
    return {
        "handle": handle,
        "method_name": method,
        "method_version": "1.0.0",
        "compactor_provider": "anthropic",
        "compactor_model": "claude-haiku-5-5",
        "season": "s1",
        "published_at": published,
        **extra,
    }


def test_rows_whose_names_run_together_get_different_pages() -> None:
    first = _row("alice", "smart-ledger", "2026-11-01T00:00:00Z")
    later = _row("alice-smart", "ledger", "2026-11-05T00:00:00Z")
    assert export.slug_of(first) == export.slug_of(later)
    rows = [later, first]  # board order is by score, not by date
    export.assign_slugs(rows)
    assert first["slug"] == "alice-smart-ledger-1.0.0-claude-haiku-5-5-s1", "first keeps its link"
    assert later["slug"] != first["slug"]
    assert str(later["slug"]).startswith(str(first["slug"]) + "-")


def test_rows_that_differ_only_by_provider_get_different_pages() -> None:
    a = _row("bob", "ledger", "2026-11-01T00:00:00Z")
    b = _row("bob", "ledger", "2026-11-01T00:00:00Z", compactor_provider="openrouter")
    export.assign_slugs([a, b])
    assert a["slug"] != b["slug"]


def test_unique_rows_keep_their_plain_slugs() -> None:
    rows = [
        _row("alice", "ledger", "2026-11-01T00:00:00Z"),
        _row("bob", "ledger", "2026-11-02T00:00:00Z"),
    ]
    export.assign_slugs(rows)
    assert [r["slug"] for r in rows] == [export.slug_of(r) for r in rows]


def test_a_reused_username_cant_replace_the_previous_owners_entry(tmp_path: Path) -> None:
    target = tmp_path / "submissions" / "alice" / "ledger"
    assert publish.owned_by(target, 1), "a new directory is free"
    target.mkdir(parents=True)
    (target / "submission.json").write_text(json.dumps({"handle": "alice", "github_id": 1}))
    assert publish.owned_by(target, 1), "the same account may resubmit"
    assert not publish.owned_by(target, 2), "another account with the same login may not"
    (target / "submission.json").write_text("not json")
    assert not publish.owned_by(target, 1)
