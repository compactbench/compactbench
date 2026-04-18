"""Tests for runtime config helpers."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from compactbench.config import default_benchmarks_dir

pytestmark = pytest.mark.unit


def test_prefers_cwd_benchmarks_when_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Developers running from a repo checkout see their local edits first."""
    (tmp_path / "benchmarks" / "public").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)

    resolved = default_benchmarks_dir()
    assert resolved == Path("benchmarks/public")
    assert resolved.resolve() == (tmp_path / "benchmarks" / "public").resolve()


def test_falls_back_to_bundled_package_data_when_cwd_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """pip-install users land on the wheel-bundled benchmarks."""
    monkeypatch.chdir(tmp_path)
    fake_package_root = tmp_path / "fake_pkg_root"
    fake_bundled = fake_package_root / "_data" / "benchmarks" / "public"
    fake_bundled.mkdir(parents=True)

    fake_init = fake_package_root / "__init__.py"
    fake_init.write_text("")

    with patch("compactbench.config.__file__", str(fake_init)):
        resolved = default_benchmarks_dir()

    assert resolved.resolve() == fake_bundled.resolve()


def test_returns_cwd_path_when_neither_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Last-resort path so the CLI's own 'no benchmarks directory' error fires."""
    monkeypatch.chdir(tmp_path)
    fake_init = tmp_path / "fake_pkg_root" / "__init__.py"
    fake_init.parent.mkdir(parents=True)
    fake_init.write_text("")

    with patch("compactbench.config.__file__", str(fake_init)):
        resolved = default_benchmarks_dir()

    assert resolved == Path("benchmarks/public")
