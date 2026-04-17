"""Elite score and tie-breaker computation.

Formulas are locked in docs/architecture/decisions.md §B4. Any change is a
scorer-version bump.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

CompressionTier = Literal["Elite-Light", "Elite-Mid", "Elite-Aggressive"]

TIER_FLOORS: dict[CompressionTier, float] = {
    "Elite-Light": 2.0,
    "Elite-Mid": 4.0,
    "Elite-Aggressive": 8.0,
}


def compression_bonus(compression_ratio: float, tier: CompressionTier) -> float:
    """Normalized bonus ``[0, 1]`` for exceeding the tier's compression floor.

    0 at exactly the floor, 1 at 2x the floor, capped.
    """
    floor = TIER_FLOORS[tier]
    if compression_ratio <= floor:
        return 0.0
    raw = (compression_ratio - floor) / floor
    return max(0.0, min(1.0, raw))


def elite_score(
    *,
    overall_score: float,
    drift_resistance: float,
    constraint_retention: float,
    compression_ratio: float,
    tier: CompressionTier,
) -> float:
    """Compute ``elite_score`` per decisions.md §B4.

    ``elite_score = 0.40 * overall + 0.30 * drift + 0.20 * constraint + 0.10 * compression_bonus``
    """
    bonus = compression_bonus(compression_ratio, tier)
    return (
        0.40 * overall_score + 0.30 * drift_resistance + 0.20 * constraint_retention + 0.10 * bonus
    )


def rank_key(
    *,
    elite_score_value: float,
    drift_resistance: float,
    constraint_retention: float,
    contradiction_rate: float,
    published_at: datetime,
) -> tuple[float, float, float, float, float]:
    """Return a sort key that orders better runs FIRST when sorted ascending.

    Primary: higher elite_score. Tie-breakers in order:
    higher drift_resistance → higher constraint_retention → lower contradiction_rate
    → earlier published_at.
    """
    return (
        -elite_score_value,
        -drift_resistance,
        -constraint_retention,
        contradiction_rate,
        published_at.timestamp(),
    )
