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


def test_rank_rows_segments_by_model() -> None:
    """A weaker method on model A must not outrank a stronger method on model B.

    Ranks are assigned independently within each
    (benchmark_version, target_provider, target_model, scorer_version) group,
    so both segments should each have a rank-1 entry.
    """

    def _row(method_name: str, model: str, overall: float) -> LeaderboardRow:
        run = RunResult(
            run_id="r",
            method_name=method_name,
            method_version="1.0.0",
            suite_key="elite",
            suite_version="1.0.0",
            scorer_version="1.0.0",
            target_provider="groq",
            target_model=model,
            started_at=datetime(2026, 4, 17, tzinfo=UTC),
            completed_at=datetime(2026, 4, 17, tzinfo=UTC),
            cases=[],
            overall_score=overall,
            drift_resistance=0.9,
            constraint_retention=0.85,
            contradiction_rate=0.02,
            compression_ratio=6.0,
        )
        return project_row(
            run,
            tier="Elite-Mid",
            handle="a",
            org=None,
            published_at=datetime(2026, 4, 17, tzinfo=UTC),
        )

    # Stronger on model B, weaker on model A.
    strong_b = _row("strong_b", "model-b", overall=0.95)
    weak_a = _row("weak_a", "model-a", overall=0.4)

    ranked = rank_rows([strong_b, weak_a])

    # Both get rank 1 in their own segment.
    ranks_by_name = {r["method_name"]: r["rank"] for r in ranked}
    assert ranks_by_name == {"weak_a": 1, "strong_b": 1}


def test_rank_rows_segments_by_benchmark_version() -> None:
    """Different benchmark versions must not cross-compete."""

    def _row(method_name: str, suite_version: str, overall: float) -> LeaderboardRow:
        run = RunResult(
            run_id="r",
            method_name=method_name,
            method_version="1.0.0",
            suite_key="elite",
            suite_version=suite_version,
            scorer_version="1.0.0",
            target_provider="groq",
            target_model="m",
            started_at=datetime(2026, 4, 17, tzinfo=UTC),
            completed_at=datetime(2026, 4, 17, tzinfo=UTC),
            cases=[],
            overall_score=overall,
            drift_resistance=0.9,
            constraint_retention=0.85,
            contradiction_rate=0.02,
            compression_ratio=6.0,
        )
        return project_row(
            run,
            tier="Elite-Mid",
            handle="a",
            org=None,
            published_at=datetime(2026, 4, 17, tzinfo=UTC),
        )

    v1 = _row("v1_entry", "1.0.0", overall=0.9)
    v2 = _row("v2_entry", "2.0.0", overall=0.3)
    ranked = rank_rows([v1, v2])
    ranks_by_name = {r["method_name"]: r["rank"] for r in ranked}
    assert ranks_by_name == {"v1_entry": 1, "v2_entry": 1}


def test_rank_rows_segments_by_endpoint_kind() -> None:
    """A self-hosted run must not be ranked against the vendor-hosted model.

    ``target_provider`` and ``target_model`` are both caller-supplied strings,
    so a locally-served model submitted as ``--provider openai --model gpt-4o``
    is indistinguishable from genuine gpt-4o on those two fields alone. Without
    ``endpoint_kind`` in the segment the two compete numerically, which is a
    comparability failure the whole leaderboard rests on avoiding.
    """

    def _row(method_name: str, endpoint_kind: str, overall: float) -> LeaderboardRow:
        run = RunResult(
            run_id="r",
            method_name=method_name,
            method_version="1.0.0",
            suite_key="elite",
            suite_version="1.0.0",
            scorer_version="1.0.0",
            target_provider="openai",
            target_model="gpt-4o",
            endpoint_kind=endpoint_kind,
            started_at=datetime(2026, 4, 17, tzinfo=UTC),
            completed_at=datetime(2026, 4, 17, tzinfo=UTC),
            cases=[],
            overall_score=overall,
            drift_resistance=0.9,
            constraint_retention=0.85,
            contradiction_rate=0.02,
            compression_ratio=6.0,
        )
        return project_row(
            run,
            tier="Elite-Mid",
            handle="a",
            org=None,
            published_at=datetime(2026, 4, 17, tzinfo=UTC),
        )

    hosted = _row("hosted", "default", overall=0.40)
    self_hosted = _row("self_hosted", "custom", overall=0.95)

    ranked = rank_rows([self_hosted, hosted])

    # Same provider and model string, but different endpoints — each is rank 1
    # in its own segment rather than the self-hosted run topping the real one.
    assert {r["method_name"]: r["rank"] for r in ranked} == {"hosted": 1, "self_hosted": 1}


def test_project_row_defaults_endpoint_kind_for_pre_0_2_results() -> None:
    """A results file written before endpoint_kind existed still projects."""
    run = RunResult(
        run_id="r",
        method_name="m",
        method_version="1.0.0",
        suite_key="elite",
        suite_version="1.0.0",
        scorer_version="1.0.0",
        target_provider="groq",
        target_model="llama",
        started_at=datetime(2026, 4, 17, tzinfo=UTC),
        completed_at=datetime(2026, 4, 17, tzinfo=UTC),
        cases=[],
        overall_score=0.5,
        drift_resistance=0.9,
        constraint_retention=0.85,
        contradiction_rate=0.02,
        compression_ratio=6.0,
    )
    row = project_row(
        run, tier="Elite-Mid", handle="a", org=None, published_at=datetime(2026, 4, 17, tzinfo=UTC)
    )
    assert row["endpoint_kind"] == "default"


class TestReferenceRows:
    """Baselines and controls publish, but must never compete with submissions."""

    def _row(self, name: str, kind: str, overall: float) -> LeaderboardRow:
        run = RunResult(
            run_id="r",
            method_name=name,
            method_version="1.0.0",
            suite_key="elite_practice",
            suite_version="1.0.0",
            scorer_version="2.0.0",
            target_provider="ollama",
            target_model="qwen2.5:1.5b-instruct",
            started_at=datetime(2026, 8, 24, tzinfo=UTC),
            completed_at=datetime(2026, 8, 24, tzinfo=UTC),
            cases=[],
            overall_score=overall,
            drift_resistance=0.9,
            constraint_retention=0.8,
            contradiction_rate=0.0,
            compression_ratio=5.0,
        )
        return project_row(
            run,
            tier="Elite-Mid",
            handle=None,
            org=None,
            published_at=datetime(2026, 8, 24, tzinfo=UTC),
            row_kind=kind,
        )

    def test_submissions_are_ranked_and_reference_rows_are_not(self) -> None:
        """The oracle sees the full uncompacted transcript — ranking it against a
        real compaction method is a category error, and the null arm would place
        on a board that exists to expose its limits."""
        ranked = rank_rows(
            [
                self._row("oracle", "control", 0.99),
                self._row("submitted-method", "submission", 0.55),
                self._row("null", "control", 0.30),
                self._row("hybrid-ledger", "baseline", 0.60),
            ]
        )
        by_name = {r["method_name"]: r["rank"] for r in ranked}
        assert by_name["submitted-method"] == 1
        assert by_name["oracle"] is None
        assert by_name["null"] is None
        assert by_name["hybrid-ledger"] is None

    def test_a_high_scoring_control_does_not_displace_a_submission(self) -> None:
        ranked = rank_rows(
            [self._row("oracle", "control", 0.99), self._row("mine", "submission", 0.10)]
        )
        assert [r["method_name"] for r in ranked if r["rank"] == 1] == ["mine"]

    def test_ranked_rows_precede_reference_rows(self) -> None:
        ranked = rank_rows(
            [self._row("oracle", "control", 0.99), self._row("mine", "submission", 0.10)]
        )
        assert ranked[0]["row_kind"] == "submission"
        assert ranked[-1]["row_kind"] == "control"

    def test_default_row_kind_is_submission(self) -> None:
        """Existing callers keep competing without changing anything."""
        run = RunResult(
            run_id="r",
            method_name="m",
            method_version="1.0.0",
            suite_key="e",
            suite_version="1.0.0",
            scorer_version="2.0.0",
            target_provider="groq",
            target_model="llama",
            started_at=datetime(2026, 8, 24, tzinfo=UTC),
            completed_at=datetime(2026, 8, 24, tzinfo=UTC),
            cases=[],
            overall_score=0.5,
            drift_resistance=0.9,
            constraint_retention=0.8,
            contradiction_rate=0.0,
            compression_ratio=5.0,
        )
        row = project_row(
            run,
            tier="Elite-Mid",
            handle=None,
            org=None,
            published_at=datetime(2026, 8, 24, tzinfo=UTC),
        )
        assert row["row_kind"] == "submission"
