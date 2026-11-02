"""Leaderboard: seasons, qualification floors, ranking, and the public row projection."""

from compactbench.leaderboard.errors import LeaderboardError, QualificationError
from compactbench.leaderboard.projection import LeaderboardRow, project_row, rank_rows
from compactbench.leaderboard.qualification import (
    MAX_READER_ERROR_RATE,
    QualificationResult,
    qualify,
)
from compactbench.leaderboard.ranking import BUDGET_TIERS, rank_key, tier_for
from compactbench.leaderboard.season import ReaderSpec, Season, load_season, season_mismatches

__all__ = [
    "BUDGET_TIERS",
    "MAX_READER_ERROR_RATE",
    "LeaderboardError",
    "LeaderboardRow",
    "QualificationError",
    "QualificationResult",
    "ReaderSpec",
    "Season",
    "load_season",
    "project_row",
    "qualify",
    "rank_key",
    "rank_rows",
    "season_mismatches",
    "tier_for",
]
