"""Elite-score and tie-breaker tests."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from compactbench.leaderboard import (
    TIER_FLOORS,
    compression_bonus,
    elite_score,
    rank_key,
)

pytestmark = pytest.mark.unit


def test_tier_floors_match_spec() -> None:
    assert TIER_FLOORS["Elite-Light"] == 2.0
    assert TIER_FLOORS["Elite-Mid"] == 4.0
    assert TIER_FLOORS["Elite-Aggressive"] == 8.0


class TestCompressionBonus:
    def test_at_floor_is_zero(self) -> None:
        assert compression_bonus(2.0, "Elite-Light") == 0.0

    def test_below_floor_is_zero(self) -> None:
        assert compression_bonus(1.5, "Elite-Light") == 0.0

    def test_at_2x_floor_is_one(self) -> None:
        assert compression_bonus(4.0, "Elite-Light") == 1.0

    def test_above_2x_floor_is_capped_at_one(self) -> None:
        assert compression_bonus(100.0, "Elite-Light") == 1.0

    def test_midway_linear(self) -> None:
        # Between floor (4) and 2x floor (8), halfway (6) should be 0.5.
        assert compression_bonus(6.0, "Elite-Mid") == pytest.approx(0.5)


class TestEliteScore:
    def test_perfect_scores_all_one(self) -> None:
        score = elite_score(
            overall_score=1.0,
            drift_resistance=1.0,
            constraint_retention=1.0,
            compression_ratio=8.0,
            tier="Elite-Mid",
        )
        # 0.40*1 + 0.30*1 + 0.20*1 + 0.10*1 = 1.0
        assert score == pytest.approx(1.0)

    def test_zero_everything(self) -> None:
        score = elite_score(
            overall_score=0.0,
            drift_resistance=0.0,
            constraint_retention=0.0,
            compression_ratio=0.0,
            tier="Elite-Light",
        )
        assert score == 0.0

    def test_weights_are_40_30_20_10(self) -> None:
        # Isolate each weight by setting others to 0.
        assert elite_score(
            overall_score=1.0,
            drift_resistance=0.0,
            constraint_retention=0.0,
            compression_ratio=0.0,
            tier="Elite-Light",
        ) == pytest.approx(0.40)
        assert elite_score(
            overall_score=0.0,
            drift_resistance=1.0,
            constraint_retention=0.0,
            compression_ratio=0.0,
            tier="Elite-Light",
        ) == pytest.approx(0.30)
        assert elite_score(
            overall_score=0.0,
            drift_resistance=0.0,
            constraint_retention=1.0,
            compression_ratio=0.0,
            tier="Elite-Light",
        ) == pytest.approx(0.20)
        assert elite_score(
            overall_score=0.0,
            drift_resistance=0.0,
            constraint_retention=0.0,
            compression_ratio=4.0,  # 2x Elite-Light floor → bonus 1.0
            tier="Elite-Light",
        ) == pytest.approx(0.10)

    def test_hand_computed_example(self) -> None:
        # overall=0.8, drift=0.9, constraint=0.85, compression=6x on Elite-Mid (bonus=0.5)
        # = 0.40*0.8 + 0.30*0.9 + 0.20*0.85 + 0.10*0.5 = 0.32 + 0.27 + 0.17 + 0.05 = 0.81
        score = elite_score(
            overall_score=0.8,
            drift_resistance=0.9,
            constraint_retention=0.85,
            compression_ratio=6.0,
            tier="Elite-Mid",
        )
        assert score == pytest.approx(0.81)


class TestRankKey:
    def test_higher_elite_score_sorts_first(self) -> None:
        t = datetime(2026, 1, 1, tzinfo=UTC)
        a = rank_key(
            elite_score_value=0.9,
            drift_resistance=0.5,
            constraint_retention=0.5,
            contradiction_rate=0.0,
            published_at=t,
        )
        b = rank_key(
            elite_score_value=0.8,
            drift_resistance=0.5,
            constraint_retention=0.5,
            contradiction_rate=0.0,
            published_at=t,
        )
        assert a < b  # `a` sorts before `b`

    def test_drift_tiebreaker_when_elite_score_ties(self) -> None:
        t = datetime(2026, 1, 1, tzinfo=UTC)
        a = rank_key(
            elite_score_value=0.8,
            drift_resistance=0.9,
            constraint_retention=0.5,
            contradiction_rate=0.0,
            published_at=t,
        )
        b = rank_key(
            elite_score_value=0.8,
            drift_resistance=0.7,
            constraint_retention=0.5,
            contradiction_rate=0.0,
            published_at=t,
        )
        assert a < b

    def test_earlier_published_wins_when_everything_else_ties(self) -> None:
        early = rank_key(
            elite_score_value=0.8,
            drift_resistance=0.5,
            constraint_retention=0.5,
            contradiction_rate=0.0,
            published_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        late = rank_key(
            elite_score_value=0.8,
            drift_resistance=0.5,
            constraint_retention=0.5,
            contradiction_rate=0.0,
            published_at=datetime(2026, 2, 1, tzinfo=UTC),
        )
        assert early < late
