"""Seasons, qualification floors, ranking, and the public projection."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from compactbench.contracts import CaseResult, CycleResult, ProbeResult, RunResult
from compactbench.leaderboard import (
    LeaderboardRow,
    load_season,
    project_row,
    qualify,
    rank_rows,
    tier_for,
)
from compactbench.runner import INCOMPLETE_RUN_NOTE
from compactbench.scoring import compute_metrics

pytestmark = pytest.mark.unit

SEASON = """
key: s1
suite: elite
suite_version: 2.0.0
difficulty: elite
drift_cycles: 4
cases_per_family: 6
budget_tokens: 2048
reader: {provider: anthropic, model: claude-haiku-5-5}
controls: true
sampling: fresh
seed_group: s1
"""


def _cases(score: float, *, over_budget: bool = False, answered: bool = True) -> list[CaseResult]:
    probe = ProbeResult(
        key="k",
        category="decision_state",
        format="single",
        origin_cycle=0,
        score=score,
        answered=answered,
    )
    cycles = [
        CycleResult(
            cycle=i,
            score=score,
            probe_results=[probe],
            source_tokens=1000,
            input_tokens=500,
            artifact_tokens=100,
            budget_tokens=2048,
            over_budget=over_budget and i == 1,
        )
        for i in range(2)
    ]
    return [CaseResult(case_id="c", family="f", seed=1, cycles=cycles, score=score)]


def _run(score: float = 0.5, **overrides: Any) -> RunResult:
    cases = overrides.pop("cases", None) or _cases(score)
    fields: dict[str, object] = {
        "run_id": "r",
        "method_name": "my-method",
        "method_version": "1",
        "suite": "elite",
        "suite_version": "2.0.0",
        "season": "s1",
        "difficulty": "elite",
        "drift_cycles": 4,
        "cases_per_family": 6,
        "compactor_provider": "openai",
        "compactor_model": "gpt-x",
        "reader_provider": "anthropic",
        "reader_model": "claude-haiku-5-5",
        "seed_group": "s1/abc",
        "budget_tokens": 2048,
        "controls": True,
        "scorer_version": "3.0.0",
        "started_at": datetime(2026, 11, 1, tzinfo=UTC),
        "completed_at": datetime(2026, 11, 1, 1, tzinfo=UTC),
        "cases": cases,
        "metrics": compute_metrics(cases),  # type: ignore[arg-type]
    }
    fields.update(overrides)
    return RunResult.model_validate(fields)


@pytest.fixture
def season_file(tmp_path: Path) -> Path:
    path = tmp_path / "s1.yaml"
    path.write_text(SEASON, encoding="utf-8")
    return path


def test_clean_run_qualifies(season_file: Path) -> None:
    outcome = qualify(_run(), season=load_season(season_file))
    assert outcome.qualified, outcome.reasons


@pytest.mark.parametrize(
    ("overrides", "fragment"),
    [
        ({"method_name": "oracle"}, "control arm"),
        ({"notes": [INCOMPLETE_RUN_NOTE]}, "incomplete"),
        ({"drift_cycles": 0}, "no drift cycles"),
        ({"budget_tokens": None}, "no token budget"),
        ({"cases": _cases(0.5, over_budget=True)}, "over the 2048-token budget"),
        ({"cases": _cases(0.5, answered=False)}, "no usable answer"),
        ({"reader_endpoint_kind": "custom"}, "custom endpoint"),
    ],
)
def test_floors(overrides: dict[str, Any], fragment: str) -> None:
    outcome = qualify(_run(**overrides))
    assert not outcome.qualified
    assert any(fragment in r for r in outcome.reasons), outcome.reasons


def test_season_pins_everything(season_file: Path) -> None:
    season = load_season(season_file)
    outcome = qualify(_run(reader_model="something-else", cases_per_family=2), season=season)
    assert not outcome.qualified
    assert any("reader_model" in r for r in outcome.reasons)
    assert any("cases_per_family" in r for r in outcome.reasons)


def test_fresh_sampling_does_not_pin_the_seed_group(season_file: Path) -> None:
    assert qualify(_run(seed_group="anything"), season=load_season(season_file)).qualified


def test_tiers() -> None:
    assert tier_for(2048) == "Standard"
    assert tier_for(1024) == "Tight"
    assert tier_for(3000) == "Custom (3000)"
    assert tier_for(None) == "Unbudgeted"


def _row(
    score: float, *, kind: str = "submission", minutes: int = 0, **run: object
) -> LeaderboardRow:
    return project_row(
        _run(score, **run),
        handle="h",
        org=None,
        published_at=datetime(2026, 11, 1, tzinfo=UTC) + timedelta(minutes=minutes),
        row_kind=kind,
    )


def test_projection_carries_public_fields_only() -> None:
    row = _row(0.4)
    assert row["tier"] == "Standard"
    assert row["by_family"] == {"f": 0.4}
    assert row["suite"] == "elite@2.0.0"
    assert "cases" in row


def test_ranking_within_segments_and_reference_rows_unranked() -> None:
    rows = [
        _row(0.3, minutes=1),
        _row(0.6, minutes=2),
        _row(0.6, minutes=0),
        _row(0.9, kind="control"),
        _row(0.5, budget_tokens=1024),
    ]
    ranked = rank_rows(rows)
    standard = [r for r in ranked if r["budget_tokens"] == 2048]
    # The two 0.6 rows can't be told apart, so they share rank 1.
    assert [r["rank"] for r in standard] == [1, 1, 3, None]
    assert standard[0]["published_at"] < standard[1]["published_at"], "earlier listed first"
    assert standard[-1]["row_kind"] == "control"
    tight = [r for r in ranked if r["budget_tokens"] == 1024]
    assert tight[0]["rank"] == 1


def test_overlapping_intervals_share_a_rank() -> None:
    def ci(row: LeaderboardRow, low: float, high: float) -> LeaderboardRow:
        return {**row, "score_ci_low": low, "score_ci_high": high}

    rows = [
        ci(_row(0.70), 0.65, 0.75),
        ci(_row(0.66, minutes=1), 0.60, 0.72),  # overlaps the leader
        ci(_row(0.40, minutes=2), 0.35, 0.45),  # clearly behind both
    ]
    assert [r["rank"] for r in rank_rows(rows)] == [1, 1, 3]
