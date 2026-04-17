"""Project run results into public leaderboard rows.

The public leaderboard never exposes hidden template content — only aggregate
metrics, method identity, and versions. Raw case outputs are not projected.
"""

from __future__ import annotations

from datetime import datetime
from typing import TypedDict

from compactbench.contracts import RunResult
from compactbench.leaderboard.ranking import (
    CompressionTier,
    elite_score,
    rank_key,
)


class LeaderboardRow(TypedDict):
    """Public row shape. Keep this stable — it is the public contract."""

    rank: int | None
    method_name: str
    method_version: str
    handle: str | None
    org: str | None
    tier: str
    benchmark_version: str
    target_provider: str
    target_model: str
    scorer_version: str
    elite_score: float
    overall_score: float
    drift_resistance: float
    constraint_retention: float
    contradiction_rate: float
    compression_ratio: float
    published_at: str


def project_row(
    run_result: RunResult,
    *,
    tier: CompressionTier,
    handle: str | None,
    org: str | None,
    published_at: datetime,
) -> LeaderboardRow:
    """Turn a qualified :class:`RunResult` into a :class:`LeaderboardRow`.

    ``rank`` is set to ``None`` here; caller assigns ranks after sorting.
    """
    score = elite_score(
        overall_score=run_result.overall_score,
        drift_resistance=run_result.drift_resistance,
        constraint_retention=run_result.constraint_retention,
        compression_ratio=run_result.compression_ratio,
        tier=tier,
    )
    return LeaderboardRow(
        rank=None,
        method_name=run_result.method_name,
        method_version=run_result.method_version,
        handle=handle,
        org=org,
        tier=tier,
        benchmark_version=f"{run_result.suite_key}@{run_result.suite_version}",
        target_provider=run_result.target_provider,
        target_model=run_result.target_model,
        scorer_version=run_result.scorer_version,
        elite_score=score,
        overall_score=run_result.overall_score,
        drift_resistance=run_result.drift_resistance,
        constraint_retention=run_result.constraint_retention,
        contradiction_rate=run_result.contradiction_rate,
        compression_ratio=run_result.compression_ratio,
        published_at=published_at.isoformat(),
    )


def rank_rows(rows: list[LeaderboardRow]) -> list[LeaderboardRow]:
    """Return ``rows`` sorted best-first with ``rank`` assigned.

    Segmentation by ``(benchmark_version, target_model)`` is the caller's
    responsibility — this function only sorts and numbers whatever it is given.
    """

    def _key(row: LeaderboardRow) -> tuple[float, float, float, float, float]:
        return rank_key(
            elite_score_value=row["elite_score"],
            drift_resistance=row["drift_resistance"],
            constraint_retention=row["constraint_retention"],
            contradiction_rate=row["contradiction_rate"],
            published_at=datetime.fromisoformat(row["published_at"]),
        )

    ranked: list[LeaderboardRow] = []
    for i, row in enumerate(sorted(rows, key=_key), start=1):
        ranked_row: LeaderboardRow = dict(row)  # pyright: ignore[reportAssignmentType]
        ranked_row["rank"] = i
        ranked.append(ranked_row)
    return ranked
