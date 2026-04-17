"""Sanity tests that confirm the package imports and wires together."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from compactbench import __version__
from compactbench.cli import app

pytestmark = pytest.mark.unit


def test_package_has_version() -> None:
    assert isinstance(__version__, str)
    assert __version__


def test_cli_shows_version() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "compactbench" in result.stdout
    assert __version__ in result.stdout


def test_cli_help_lists_core_commands() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for command in ("run", "generate", "score", "submit", "providers", "suites"):
        assert command in result.stdout
