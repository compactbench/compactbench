"""Project run results into public leaderboard rows.

Rows carry aggregate metrics, method identity and versions only — never case
content — so they are safe to publish for hidden suites.
"""

from __future__ import annotations

from datetime import datetime
from typing import TypedDict

from compactbench.contracts import RunResult
from compactbench.leaderboard.ranking import rank_key, tier_for


class LeaderboardRow(TypedDict):
    """Public row shape. Keep this stable — published leaderboard data uses it."""

    rank: int | None
    # "submission" — ranked. "baseline" — a maintainer reference run of a
    # built-in or provider-native method; shown, never ranked. "control" —
    # oracle / null / truncate-last-n; shown, never ranked.
    row_kind: str
    method_name: str
    method_version: str
    handle: str | None
    org: str | None
    suite: str
    season: str | None
    scorer_version: str
    reader_provider: str
    reader_model: str
    reader_endpoint_kind: str
    reader_effort: str | None
    compactor_provider: str
    compactor_model: str
    # Display name a submitter gave their own (custom-endpoint) model; None otherwise.
    model_label: str | None
    compactor_endpoint_kind: str
    budget_tokens: int | None
    tier: str
    score: float
    score_ci_low: float
    score_ci_high: float
    normalized_score: float | None
    drift_resistance: float
    decay: float
    stale_rate: float
    trap_rate: float
    hallucination_rate: float
    compression_ratio: float
    mean_artifact_tokens: float
    by_family: dict[str, float]
    by_cycle: list[float]
    method_tokens: int | None
    cases: int
    published_at: str


def project_row(
    run: RunResult,
    *,
    handle: str | None,
    org: str | None,
    published_at: datetime,
    row_kind: str = "submission",
    model_label: str | None = None,
) -> LeaderboardRow:
    """Turn a :class:`RunResult` into a :class:`LeaderboardRow` (``rank`` assigned later)."""
    m = run.metrics
    method_tokens = sum(
        cycle.compactor_usage.total_tokens
        for case in run.cases
        for cycle in case.cycles
        if cycle.compactor_usage is not None
    )
    return LeaderboardRow(
        rank=None,
        row_kind=row_kind,
        method_name=run.method_name,
        method_version=run.method_version,
        handle=handle,
        org=org,
        suite=f"{run.suite}@{run.suite_version}",
        season=run.season,
        scorer_version=run.scorer_version,
        reader_provider=run.reader_provider,
        reader_model=run.reader_model,
        reader_endpoint_kind=run.reader_endpoint_kind,
        reader_effort=run.reader_effort,
        compactor_provider=run.compactor_provider,
        compactor_model=run.compactor_model,
        model_label=model_label,
        compactor_endpoint_kind=run.compactor_endpoint_kind,
        budget_tokens=run.budget_tokens,
        tier=tier_for(run.budget_tokens),
        score=m.score,
        score_ci_low=m.score_ci_low,
        score_ci_high=m.score_ci_high,
        normalized_score=m.normalized_score,
        drift_resistance=m.drift_resistance,
        decay=m.decay,
        stale_rate=m.stale_rate,
        trap_rate=m.trap_rate,
        hallucination_rate=m.hallucination_rate,
        compression_ratio=m.compression_ratio,
        mean_artifact_tokens=m.mean_artifact_tokens,
        by_family={family: fm.score for family, fm in m.by_family.items()},
        by_cycle=list(m.by_cycle),
        method_tokens=method_tokens or None,
        cases=len(run.cases),
        published_at=published_at.isoformat(),
    )


_Segment = tuple[str, str, str, str, str, str, int]


def _segment(row: LeaderboardRow) -> _Segment:
    """Rows only compete within one suite, scorer, reader and budget."""
    return (
        row["suite"],
        row["scorer_version"],
        row["reader_provider"],
        row["reader_model"],
        row["reader_endpoint_kind"],
        row["reader_effort"] or "",
        row["budget_tokens"] or 0,
    )


def _key(row: LeaderboardRow) -> tuple[float, float, float, float]:
    return rank_key(
        score=row["score"],
        drift_resistance=row["drift_resistance"],
        stale_rate=row["stale_rate"],
        published_at=datetime.fromisoformat(row["published_at"]),
    )


def rank_rows(rows: list[LeaderboardRow]) -> list[LeaderboardRow]:
    """Return ``rows`` best-first, ranks assigned within each segment.

    A row's rank is one plus the number of rows whose whole 95% interval lies
    above its own, so methods whose intervals overlap share a rank: the board
    never claims an order the samples can't support. Display order within a
    shared rank still follows the tie-breaks. Reference rows (baselines and
    controls) follow the ranked rows of their segment, ordered by score, with
    ``rank`` left as ``None``.
    """
    segments: dict[_Segment, list[LeaderboardRow]] = {}
    for row in rows:
        segments.setdefault(_segment(row), []).append(row)

    ordered: list[LeaderboardRow] = []
    for segment in sorted(segments):
        members = segments[segment]
        competing = sorted((r for r in members if r["row_kind"] == "submission"), key=_key)
        reference = sorted((r for r in members if r["row_kind"] != "submission"), key=_key)
        for row in competing:
            ranked: LeaderboardRow = dict(row)  # pyright: ignore[reportAssignmentType]
            ranked["rank"] = 1 + sum(
                1 for other in competing if other["score_ci_low"] > row["score_ci_high"]
            )
            ordered.append(ranked)
        for row in reference:
            unranked: LeaderboardRow = dict(row)  # pyright: ignore[reportAssignmentType]
            unranked["rank"] = None
            ordered.append(unranked)
    return ordered
