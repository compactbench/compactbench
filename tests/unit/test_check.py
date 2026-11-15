"""``compactbench check``: snapshots, the regression gate and the report."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from compactbench.check import MARKER, compare, load_snapshot, render_markdown
from compactbench.cli import app

pytestmark = pytest.mark.unit

runner = CliRunner()

MOCK = [
    "--provider",
    "mock",
    "--model",
    "mock-deterministic",
    "--reader-provider",
    "mock",
    "--reader-model",
    "mock-deterministic",
]


def _snap(score: float, **changes: Any) -> dict[str, Any]:
    snap: dict[str, Any] = {
        "schema": 1,
        "method": "my-method",
        "method_version": "1.0.0",
        "model": "anthropic/claude-haiku-5-5",
        "suite": "practice@2.0.1",
        "difficulty": "elite",
        "drift_cycles": 4,
        "cases": 4,
        "seed_group": "ci",
        "budget_tokens": 1024,
        "reader": "anthropic/claude-haiku-5-5@high",
        "scorer": "3.0.0",
        "score": score,
        "score_ci_low": score - 0.05,
        "score_ci_high": score + 0.05,
        "by_cycle": [score + 0.1, score],
        "by_family": {"decision_override": score, "numeric_precision": score - 0.1},
        "reader_error_rate": 0.0,
    }
    snap.update(changes)
    return snap


def test_no_baseline_passes_and_says_how_to_record_one() -> None:
    verdict = compare(_snap(0.4), None, max_drop=None, min_score=None)
    assert verdict.passed
    assert verdict.change is None
    report = render_markdown(_snap(0.4), None, verdict, max_drop=None, min_score=None)
    assert "--update-baseline" in report
    assert "Baseline" not in report


def test_a_drop_within_the_limit_passes() -> None:
    verdict = compare(_snap(0.47), _snap(0.50), max_drop=5.0, min_score=None)
    assert verdict.passed
    assert verdict.change == pytest.approx(-0.03)


def test_a_drop_past_the_limit_fails() -> None:
    verdict = compare(_snap(0.44), _snap(0.50), max_drop=5.0, min_score=None)
    assert not verdict.passed
    assert "dropped 6.0 points" in verdict.reasons[0]
    report = render_markdown(_snap(0.44), _snap(0.50), verdict, max_drop=5.0, min_score=None)
    assert "check: failed" in report
    assert "| Overall | **44.0** | 39.0-49.0 | 50.0 | -6.0 |" in report
    assert "| `numeric_precision` | 34.0 | 40.0 | -6.0 |" in report


def test_an_improvement_shows_a_plus_sign() -> None:
    verdict = compare(_snap(0.55), _snap(0.50), max_drop=5.0, min_score=None)
    assert verdict.passed
    report = render_markdown(_snap(0.55), _snap(0.50), verdict, max_drop=5.0, min_score=None)
    assert "| +5.0 |" in report


def test_min_score_applies_with_or_without_a_baseline() -> None:
    assert not compare(_snap(0.30), None, max_drop=None, min_score=35).passed
    assert compare(_snap(0.40), None, max_drop=None, min_score=35).passed


def test_a_baseline_from_different_settings_is_not_compared() -> None:
    verdict = compare(_snap(0.60), _snap(0.50, cases=8), max_drop=5.0, min_score=None)
    assert not verdict.passed
    assert verdict.change is None
    assert verdict.mismatch == ["cases: baseline 8, now 4"]
    report = render_markdown(
        _snap(0.60), _snap(0.50, cases=8), verdict, max_drop=5.0, min_score=None
    )
    assert "not comparable" in report
    assert "Baseline" not in report.split("#### By family")[0]


def test_a_new_method_or_model_is_still_compared() -> None:
    other = _snap(0.50, method="old-method", model="openai/gpt-5-mini")
    assert compare(_snap(0.49), other, max_drop=5.0, min_score=None).passed


def test_the_marker_is_only_added_on_request() -> None:
    verdict = compare(_snap(0.4), None, max_drop=None, min_score=None)
    plain = render_markdown(_snap(0.4), None, verdict, max_drop=None, min_score=None)
    marked = render_markdown(_snap(0.4), None, verdict, max_drop=None, min_score=None, marker=True)
    assert MARKER not in plain
    assert marked.startswith(f"{MARKER} my-method anthropic/claude-haiku-5-5 -->\n")


def test_load_snapshot_rejects_other_files(tmp_path: Path) -> None:
    path = tmp_path / "x.json"
    path.write_text('{"score": 0.5}', encoding="utf-8")
    with pytest.raises(ValueError, match="not a compactbench check baseline"):
        load_snapshot(path)
    path.write_text("not json", encoding="utf-8")
    with pytest.raises(ValueError, match="not valid JSON"):
        load_snapshot(path)


def test_cli_records_then_compares_a_baseline(tmp_path: Path) -> None:
    base = tmp_path / "baseline.json"
    common = ["check", "--method", "built-in:null", "--suite", "starter", "--cases", "1", *MOCK]
    common += ["--output", str(tmp_path / "r.jsonl")]

    recorded = runner.invoke(app, [*common, "--baseline", str(base), "--update-baseline"])
    assert recorded.exit_code == 0, recorded.output
    saved = load_snapshot(base)
    assert saved["method"] == "null"
    assert saved["suite"].startswith("starter@")
    assert saved["cases"] == len(saved["by_family"])  # one case per starter family

    assert "Recorded as the new baseline" in recorded.output
    assert "No baseline yet" not in recorded.output

    summary = tmp_path / "summary.md"
    out = tmp_path / "check.json"
    again = runner.invoke(
        app, [*common, "--baseline", str(base), "--summary", str(summary), "--json", str(out)]
    )
    assert again.exit_code == 0, again.output
    assert summary.read_text(encoding="utf-8").startswith(f"{MARKER} null mock/")
    result = json.loads(out.read_text(encoding="utf-8"))
    assert result["check"]["passed"] is True
    assert result["check"]["change"] == 0.0


def test_cli_fails_when_the_baseline_does_not_match(tmp_path: Path) -> None:
    base = tmp_path / "baseline.json"
    base.write_text(json.dumps(_snap(0.5)), encoding="utf-8")
    result = runner.invoke(
        app,
        [
            "check",
            "--method",
            "built-in:null",
            "--suite",
            "starter",
            "--cases",
            "1",
            *MOCK,
            "--output",
            str(tmp_path / "r.jsonl"),
            "--baseline",
            str(base),
        ],
    )
    assert result.exit_code == 1
    assert "not comparable" in result.output


def test_cli_update_baseline_needs_a_path() -> None:
    result = runner.invoke(app, ["check", "--method", "built-in:null", "--update-baseline"])
    assert result.exit_code == 2


def test_cli_estimate_makes_no_calls() -> None:
    result = runner.invoke(app, ["check", "--method", "built-in:naive-summary", "--estimate"])
    assert result.exit_code == 0, result.output
    assert "Run plan" in result.output


def test_one_case_has_no_interval() -> None:
    snap = _snap(0.5, cases=1, score_ci_low=0.5, score_ci_high=0.5)
    verdict = compare(snap, None, max_drop=None, min_score=None)
    report = render_markdown(snap, None, verdict, max_drop=None, min_score=None)
    assert "| Overall | **50.0** | - |" in report
