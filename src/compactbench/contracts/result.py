"""Scoring and run-result contracts.

Metric shapes mirror the formulas locked in docs/architecture/decisions.md §B3.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ItemScore(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    item_key: str
    item_type: str
    score: float = Field(ge=0.0, le=1.0)
    weight: float = Field(gt=0.0)
    check_type: str
    details: dict[str, Any] = Field(default_factory=dict)


class Scorecard(BaseModel):
    """Per-cycle aggregated scores."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    cycle_number: int = Field(ge=0)
    cycle_score: float = Field(ge=0.0, le=1.0)
    penalized_cycle_score: float = Field(ge=0.0, le=1.0)
    contradiction_rate: float = Field(ge=0.0, le=1.0)
    compression_ratio: float = Field(ge=0.0)
    item_scores: list[ItemScore]


class CycleResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    cycle_number: int = Field(ge=0)
    scorecard: Scorecard
    drift_delta: float | None = None
    latency_ms: int | None = None


class CaseResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str
    template_key: str
    seed: int
    cycles: list[CycleResult]
    case_score: float = Field(ge=0.0, le=1.0)
    drift_resistance: float = Field(ge=0.0, le=1.0)


class RunResult(BaseModel):
    """Top-level run artifact. Serialized one per line in results.jsonl."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str
    method_name: str
    method_version: str
    suite_key: str
    suite_version: str
    scorer_version: str
    target_provider: str
    target_model: str
    started_at: datetime
    completed_at: datetime
    cases: list[CaseResult]
    overall_score: float = Field(ge=0.0, le=1.0)
    drift_resistance: float = Field(ge=0.0, le=1.0)
    constraint_retention: float = Field(ge=0.0, le=1.0)
    contradiction_rate: float = Field(ge=0.0, le=1.0)
    compression_ratio: float = Field(ge=0.0)
    notes: list[str] = Field(default_factory=list)
