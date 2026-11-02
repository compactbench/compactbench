"""Budget tiers and the ranking order.

The headline is the family-balanced ``score``. Compression is not a bonus:
every ranked run compacts to the same token budget, and tiers are separate
boards. Ties break on drift resistance, then on stale rate (lower is better),
then on who published first.
"""

from __future__ import annotations

from datetime import datetime

#: Named token budgets. A run's tier is the name of its budget, if it has one.
BUDGET_TIERS: dict[str, int] = {
    "Roomy": 4096,
    "Standard": 2048,
    "Tight": 1024,
}


def tier_for(budget_tokens: int | None) -> str:
    """Tier name for ``budget_tokens`` (``"Custom (N)"`` for anything else)."""
    if budget_tokens is None:
        return "Unbudgeted"
    for name, tokens in BUDGET_TIERS.items():
        if tokens == budget_tokens:
            return name
    return f"Custom ({budget_tokens})"


def rank_key(
    *,
    score: float,
    drift_resistance: float,
    stale_rate: float,
    published_at: datetime,
) -> tuple[float, float, float, float]:
    """Sort key that orders better runs first when sorted ascending."""
    return (-score, -drift_resistance, stale_rate, published_at.timestamp())
