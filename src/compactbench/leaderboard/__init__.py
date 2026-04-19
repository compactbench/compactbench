"""Leaderboard ranking, qualification, and public projection.

Formulas locked in docs/architecture/decisions.md §B4.
Implemented in WO-008.
"""

from compactbench.leaderboard.errors import LeaderboardError, QualificationError
from compactbench.leaderboard.projection import LeaderboardRow, project_row, rank_rows
from compactbench.leaderboard.qualification import (
    MAX_CONTRADICTION_RATE,
    MIN_FAMILY_MEAN_SCORE,
    QualificationResult,
    qualify,
)
from compactbench.leaderboard.ranking import (
    TIER_FLOORS,
    CompressionTier,
    compression_bonus,
    elite_score,
    rank_key,
)

__all__ = [
    "MAX_CONTRADICTION_RATE",
    "MIN_FAMILY_MEAN_SCORE",
    "TIER_FLOORS",
    "CompressionTier",
    "LeaderboardError",
    "LeaderboardRow",
    "QualificationError",
    "QualificationResult",
    "compression_bonus",
    "elite_score",
    "project_row",
    "qualify",
    "rank_key",
    "rank_rows",
]
