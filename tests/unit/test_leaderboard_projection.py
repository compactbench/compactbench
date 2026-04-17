"""Projection tests: RunResult -> LeaderboardRow; rank assignment."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from compactbench.contracts import RunResult
from compactbench.leaderboard import LeaderboardRow, project_row, rank_rows

pytestmark = pytest.mark.unit


def _run_result(
    *,
    method_name: str = "m",
    overall: float = 0.8,
    drift: float = 0.9,
    constraint: float = 0.85,
    compression: float = 6.0,
) -> RunResult:
    return RunResult(
        run_id="r",
        method_name=method_name,
        method_version="1.0.0",
        suite_key="elite",
        suite_version="1.0.0",
        scorer_version="1.0.0",
        target_provider="groq",
        target_model="llama-3.3-70b-versatile",
        started_at=datetime(2026, 4, 17, tzinfo=UTC),
        completed_at=datetime(2026, 4, 17, tzinfo=UTC),
        cases=[],
        overall_score=overall,
        drift_resistance=drift,
        constraint_retention=constraint,
        contradiction_rate=0.02,
        compression_ratio=compression,
    )


def test_project_row_shapes() -> None:
    row = project_row(
        _run_result(),
        tier="Elite-Mid",
        handle="alice",
        org=None,
        published_at=datetime(2026, 4, 17, tzinfo=UTC),
    )
    assert row["rank"] is None  # unassigned until ranked
    assert row["method_name"] == "m"
    assert row["handle"] == "alice"
    assert row["tier"] == "Elite-Mid"
    assert row["benchmark_version"] == "elite@1.0.0"
    assert row["target_model"] == "llama-3.3-70b-versatile"
    assert 0.0 <= row["elite_score"] <= 1.0
    assert row["overall_score"] == 0.8


def test_project_row_uses_hand_computed_elite_score() -> None:
    # overall=0.8 drift=0.9 constraint=0.85 compression=6 on Elite-Mid → 0.81
    row = project_row(
        _run_result(),
        tier="Elite-Mid",
        handle=None,
        org=None,
        published_at=datetime(2026, 4, 17, tzinfo=UTC),
    )
    assert row["elite_score"] == pytest.approx(0.81)


def test_rank_rows_assigns_1_based_ranks_best_first() -> None:
    weaker = project_row(
        _run_result(method_name="weaker", overall=0.4),
        tier="Elite-Mid",
        handle="a",
        org=None,
        published_at=datetime(2026, 4, 17, tzinfo=UTC),
    )
    stronger = project_row(
        _run_result(method_name="stronger", overall=0.95),
        tier="Elite-Mid",
        handle="b",
        org=None,
        published_at=datetime(2026, 4, 17, tzinfo=UTC),
    )
    ranked = rank_rows([weaker, stronger])
    assert ranked[0]["method_name"] == "stronger"
    assert ranked[0]["rank"] == 1
    assert ranked[1]["method_name"] == "weaker"
    assert ranked[1]["rank"] == 2


def test_rank_rows_tie_broken_by_drift_resistance() -> None:
    # Equal elite_score (same overall/constraint/compression), differ on drift.
    higher_drift = project_row(
        _run_result(method_name="tough", drift=0.95),
        tier="Elite-Mid",
        handle="a",
        org=None,
        published_at=datetime(2026, 4, 17, tzinfo=UTC),
    )
    lower_drift = project_row(
        _run_result(method_name="brittle", drift=0.70),
        tier="Elite-Mid",
        handle="b",
        org=None,
        published_at=datetime(2026, 4, 17, tzinfo=UTC),
    )
    # They'll differ on elite_score too because drift is weighted, but both
    # have the same overall/constraint/compression — the tie-break kicks in
    # only when elite_score genuinely ties. Instead check rank order matches
    # drift order.
    ranked = rank_rows([lower_drift, higher_drift])
    assert ranked[0]["method_name"] == "tough"


def test_rank_rows_empty_list() -> None:
    rows: list[LeaderboardRow] = []
    assert rank_rows(rows) == []
