"""Scoring and run-result contracts.

Metric shapes mirror the formulas locked in docs/architecture/decisions.md §B3.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TokenUsage(BaseModel):
    """Aggregate token accounting across one or more provider calls.

    Fields are additive — ``a + b`` returns a new ``TokenUsage`` whose fields are
    the element-wise sum, so per-cycle usage can be rolled up to per-case and
    per-run totals without any custom logic outside this contract.

    ``prompt_tokens`` covers *all* input tokens submitted to a provider,
    regardless of whether they were billed at the full rate, the cached-prefix
    rate, or a reserved-but-unused rate. This intentionally matches what the
    provider reports in its ``usage`` field — downstream cost models that want
    cache-aware billing should subtract ``cached_prompt_tokens`` themselves.

    ``cached_prompt_tokens`` is the subset of ``prompt_tokens`` that providers
    reported as a cache hit (Anthropic's ``cache_read_input_tokens``, OpenAI's
    ``cached_tokens``). Defaults to 0 for providers that do not distinguish.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    cached_prompt_tokens: int = Field(default=0, ge=0)
    call_count: int = Field(default=0, ge=0)

    @property
    def total_tokens(self) -> int:
        """Sum of prompt + completion tokens, matching provider ``total_tokens``."""
        return self.prompt_tokens + self.completion_tokens

    def __add__(self, other: TokenUsage) -> TokenUsage:
        return TokenUsage(
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
            cached_prompt_tokens=self.cached_prompt_tokens + other.cached_prompt_tokens,
            call_count=self.call_count + other.call_count,
        )


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
    # ``None`` means "not recorded for this cycle" and is distinct from a
    # ``TokenUsage`` with all-zero fields (which means "zero tokens actually
    # billed" — e.g. cache-only or offline providers). Older ``results.jsonl``
    # files from before token telemetry existed will deserialize with ``None``.
    token_usage: TokenUsage | None = None


class CaseResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str
    template_key: str
    seed: int
    cycles: list[CycleResult]
    case_score: float = Field(ge=0.0, le=1.0)
    drift_resistance: float = Field(ge=0.0, le=1.0)
    token_usage: TokenUsage | None = None


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
    token_usage: TokenUsage | None = None
    notes: list[str] = Field(default_factory=list)
