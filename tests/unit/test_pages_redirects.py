"""Redirects from the old GitHub Pages docs to compactbench.com."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "pages_redirects", ROOT / "scripts" / "pages_redirects.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


redirects = _load()


def test_every_old_docs_page_has_a_new_address() -> None:
    pages = {
        str(path.relative_to(ROOT / "docs").with_suffix("")).removesuffix("index").rstrip("/")
        for path in (ROOT / "docs").rglob("*.md")
        if "data" not in path.relative_to(ROOT / "docs").parts
    }
    missing = sorted(pages - set(redirects.MOVED))
    assert not missing, f"add these to MOVED in scripts/pages_redirects.py: {missing}"


def test_pages_point_at_compactbench_com(tmp_path: Path) -> None:
    assert redirects.main(["pages_redirects.py", str(tmp_path)]) == 0
    submitting = (tmp_path / "submitting" / "index.html").read_text(encoding="utf-8")
    assert 'href="https://compactbench.com/submit"' in submitting
    assert (tmp_path / "404.html").exists()
