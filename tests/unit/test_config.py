"""Tests for runtime config helpers."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from compactbench.config import load_dotenv

pytestmark = pytest.mark.unit


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
