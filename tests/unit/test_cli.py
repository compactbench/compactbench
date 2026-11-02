"""CLI commands, offline."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from compactbench.cli import app
from compactbench.runner.persistence import read_run_start

pytestmark = pytest.mark.unit

runner = CliRunner()


def test_suites_and_families_list() -> None:
    suites = runner.invoke(app, ["suites", "list"])
    assert suites.exit_code == 0, suites.output
    assert "starter" in suites.output
    assert "practice" in suites.output
    families = runner.invoke(app, ["families", "list"])
    assert families.exit_code == 0
    assert "decision_override" in families.output


def test_generate_text(tmp_path: Path) -> None:
    out = tmp_path / "case.txt"
    result = runner.invoke(
        app,
        [
            "generate",
            "--family",
            "entity_confusion",
            "--seed",
            "3",
            "--difficulty",
            "easy",
            "--text",
            "--output",
            str(out),
        ],
    )
    assert result.exit_code == 0, result.output
    text = out.read_text(encoding="utf-8")
    assert "===== cycle 0" in text
    assert "probes after compaction 0" in text


def test_generate_unknown_family() -> None:
    result = runner.invoke(app, ["generate", "--family", "nope"])
    assert result.exit_code == 1


def test_estimate_makes_no_calls() -> None:
    result = runner.invoke(
        app,
        [
            "run",
            "--method",
            "built-in:naive-summary",
            "--suite",
            "starter",
            "--cases",
            "1",
            "--estimate",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Run plan" in result.output


def test_run_score_qualify_round_trip(tmp_path: Path) -> None:
    out = tmp_path / "r.jsonl"
    result = runner.invoke(
        app,
        [
            "run",
            "--method",
            "built-in:null",
            "--suite",
            "starter",
            "--cases",
            "1",
            "--output",
            str(out),
        ],
    )
    assert result.exit_code == 0, result.output
    scored = runner.invoke(app, ["score", "--results", str(out)])
    assert scored.exit_code == 0, scored.output
    assert "By family" in scored.output
    qualified = runner.invoke(app, ["qualify", "--results", str(out)])
    assert qualified.exit_code == 1
    assert "control arm" in qualified.output


def test_resuming_a_fresh_sample_season_run_keeps_its_sample(tmp_path: Path) -> None:
    season = tmp_path / "s.yaml"
    season.write_text(
        "key: sx\nsuite: starter\nsuite_version: '2.0.1'\ndifficulty: easy\ndrift_cycles: 1\n"
        "cases_per_family: 1\nbudget_tokens: 2048\n"
        "reader: {provider: mock, model: mock-deterministic}\ncontrols: false\nsampling: fresh\n",
        encoding="utf-8",
    )
    out = tmp_path / "r.jsonl"
    args = ["run", "--season", str(season), "--method", "built-in:null", "--output", str(out)]
    assert runner.invoke(app, args).exit_code == 0
    first = read_run_start(out)
    assert first is not None
    resumed = runner.invoke(app, [*args, "--resume"])
    assert resumed.exit_code == 0, resumed.output
    again = read_run_start(out)
    assert again is not None
    assert again.seed_group == first.seed_group


def test_keys_generate_writes_the_private_key_to_a_private_file(tmp_path: Path) -> None:
    from compactbench.sealing import open_sealed, public_key_of, seal

    out = tmp_path / "season.key"
    result = runner.invoke(app, ["keys", "generate", "--private-out", str(out)])
    assert result.exit_code == 0, result.output
    private = out.read_text().strip()
    public = result.output.strip()
    assert private not in result.output
    assert out.stat().st_mode & 0o777 == 0o600
    assert public_key_of(private) == public
    assert open_sealed(private, seal(public, b"k", context="c"), context="c") == b"k"
    again = runner.invoke(app, ["keys", "generate", "--private-out", str(out)])
    assert again.exit_code == 1
    assert out.read_text().strip() == private
