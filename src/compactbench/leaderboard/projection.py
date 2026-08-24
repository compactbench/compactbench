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
    # What this row is, and whether it competes:
    #   "submission" — a submitted method; ranked.
    #   "baseline"   — a maintainer reference run of a built-in method. Published
    #                  so the board is never empty and so submitters have
    #                  something to beat, but not ranked against submissions.
    #   "control"    — oracle / null / truncate-last-n. Reference points that
    #                  make every other number readable; never ranked.
    row_kind: str
    method_name: str
    method_version: str
    handle: str | None
    org: str | None
    tier: str
    benchmark_version: str
    target_provider: str
    target_model: str
    # "default" = the provider's own endpoint; "custom" = an OpenAI-compatible
    # or remote host. Part of the ranking segment: a self-hosted model submitted
    # under a hosted model's name must never be ranked against the real thing.
    endpoint_kind: str
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
    row_kind: str = "submission",
) -> LeaderboardRow:
    """Turn a :class:`RunResult` into a :class:`LeaderboardRow`.

    ``rank`` is set to ``None`` here; caller assigns ranks after sorting.
    ``row_kind`` distinguishes ranked submissions from published reference rows
    (maintainer baselines and control arms), which appear on the board but never
    compete against submissions.
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
        row_kind=row_kind,
        method_name=run_result.method_name,
        method_version=run_result.method_version,
        handle=handle,
        org=org,
        tier=tier,
        benchmark_version=f"{run_result.suite_key}@{run_result.suite_version}",
        target_provider=run_result.target_provider,
        target_model=run_result.target_model,
        endpoint_kind=run_result.endpoint_kind,
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
    """Return ``rows`` sorted best-first with ``rank`` assigned within each segment.

    Ranks are computed **independently within each ``(benchmark_version,
    target_provider, target_model, scorer_version)`` group** so Llama 3.3 70B
    methods never compete numerically with Claude 3.5 Haiku methods, etc. The
    output list is returned in ``(segment, rank ascending)`` order.
    """

    def _segment(row: LeaderboardRow) -> tuple[str, str, str, str, str]:
        return (
            row["benchmark_version"],
            row["target_provider"],
            row["target_model"],
            row["endpoint_kind"],
            row["scorer_version"],
        )

    def _key(row: LeaderboardRow) -> tuple[float, float, float, float, float]:
        return rank_key(
            elite_score_value=row["elite_score"],
            drift_resistance=row["drift_resistance"],
            constraint_retention=row["constraint_retention"],
            contradiction_rate=row["contradiction_rate"],
            published_at=datetime.fromisoformat(row["published_at"]),
        )

    # Reference rows (maintainer baselines and control arms) are published but
    # never numbered: ranking `oracle` — which sees the full uncompacted
    # transcript — against a real compaction method is a category error, and
    # `null` would place on a board it exists to expose the limits of. They are
    # emitted after the ranked rows within each segment, ordered by score.
    competing = [r for r in rows if r["row_kind"] == "submission"]
    reference = [r for r in rows if r["row_kind"] != "submission"]

    # Group first, then sort + number inside each group.
    segments: dict[tuple[str, str, str, str, str], list[LeaderboardRow]] = {}
    for row in competing:
        segments.setdefault(_segment(row), []).append(row)

    ranked: list[LeaderboardRow] = []
    for segment_key in sorted(segments):
        for i, row in enumerate(sorted(segments[segment_key], key=_key), start=1):
            ranked_row: LeaderboardRow = dict(row)  # pyright: ignore[reportAssignmentType]
            ranked_row["rank"] = i
            ranked.append(ranked_row)

    for row in sorted(reference, key=lambda r: (_segment(r), _key(r))):
        unranked: LeaderboardRow = dict(row)  # pyright: ignore[reportAssignmentType]
        unranked["rank"] = None
        ranked.append(unranked)
    return ranked
