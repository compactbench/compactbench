"""Tests for runtime config helpers."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from compactbench.config import default_benchmarks_dir, load_dotenv

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


class TestLoadDotenv:
    """`.env` is the documented way to supply keys; it must actually work."""

    def test_loads_compactbench_variables(self, tmp_path: Path) -> None:
        env = tmp_path / ".env"
        env.write_text("COMPACTBENCH_GROQ_API_KEY=abc123\n", encoding="utf-8")
        applied = load_dotenv(env)
        assert applied == {"COMPACTBENCH_GROQ_API_KEY": "abc123"}
        assert os.environ["COMPACTBENCH_GROQ_API_KEY"] == "abc123"

    def test_real_environment_wins_over_dotenv(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An explicit export must not be silently overridden by a checked-in file."""
        monkeypatch.setenv("COMPACTBENCH_GROQ_API_KEY", "from-shell")
        env = tmp_path / ".env"
        env.write_text("COMPACTBENCH_GROQ_API_KEY=from-file\n", encoding="utf-8")
        assert load_dotenv(env) == {}
        assert os.environ["COMPACTBENCH_GROQ_API_KEY"] == "from-shell"

    def test_ignores_unprefixed_variables(self, tmp_path: Path) -> None:
        """A .env often holds unrelated secrets; do not import them."""
        env = tmp_path / ".env"
        env.write_text("AWS_SECRET_ACCESS_KEY=nope\nCOMPACTBENCH_OK=yes\n", encoding="utf-8")
        assert load_dotenv(env) == {"COMPACTBENCH_OK": "yes"}
        # Asserting absence would be wrong — CI runners legitimately export AWS
        # credentials. What matters is that the .env value was not imported.
        assert os.environ.get("AWS_SECRET_ACCESS_KEY") != "nope"

    @pytest.mark.parametrize(
        ("line", "expected"),
        [
            ("COMPACTBENCH_X=plain", "plain"),
            ('COMPACTBENCH_X="double quoted"', "double quoted"),
            ("COMPACTBENCH_X='single quoted'", "single quoted"),
            ("export COMPACTBENCH_X=exported", "exported"),
            ("  COMPACTBENCH_X = spaced  ", "spaced"),
        ],
    )
    def test_parses_common_dotenv_shapes(self, tmp_path: Path, line: str, expected: str) -> None:
        env = tmp_path / ".env"
        env.write_text(line + "\n", encoding="utf-8")
        assert load_dotenv(env) == {"COMPACTBENCH_X": expected}

    def test_skips_comments_and_blank_lines(self, tmp_path: Path) -> None:
        env = tmp_path / ".env"
        env.write_text("# a comment\n\nCOMPACTBENCH_Y=1\n", encoding="utf-8")
        assert load_dotenv(env) == {"COMPACTBENCH_Y": "1"}

    def test_missing_file_is_not_an_error(self, tmp_path: Path) -> None:
        assert load_dotenv(tmp_path / "nope.env") == {}
