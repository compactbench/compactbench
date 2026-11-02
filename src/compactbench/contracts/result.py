"""Scoring and run-result contracts.

Every number here is derived mechanically from structured probe answers; see
``docs/methodology.md`` for the definitions.
"""

from __future__ import annotations

from datetime import datetime

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


def add_usage(a: TokenUsage | None, b: TokenUsage | None) -> TokenUsage | None:
    """Sum two optional usages, keeping ``None`` only when both are ``None``."""
    if a is None:
        return b
    if b is None:
        return a
    return a + b


class ProbeResult(BaseModel):
    """How the reader did on one probe at one cycle. Holds no question text."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str
    category: str
    format: str
    origin_cycle: int = Field(ge=0)
    score: float = Field(ge=0.0, le=1.0)
    answered: bool = Field(description="False when the reader gave no parseable answer.")
    stale: bool = Field(default=False, description="The answer matched a superseded value.")
    abstained: bool = Field(default=False, description="The reader answered 'not stated'.")
    expects_abstention: bool = Field(default=False)
    stale_possible: bool = Field(default=False, description="The probe had superseded answers.")
    trapped: bool = Field(default=False, description="The answer matched a decoy-only value.")
    trap_possible: bool = Field(default=False, description="The probe offered decoy answers.")
    family: str = Field(default="", description="Asking family in a mixed case; else empty.")
    oracle_score: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Same probe answered from the full conversation."
    )
    null_score: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Same probe answered from nothing."
    )


class CycleResult(BaseModel):
    """One compaction plus the reader's answers to that cycle's probes."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    cycle: int = Field(ge=0)
    score: float = Field(ge=0.0, le=1.0)
    probe_results: list[ProbeResult]
    source_tokens: int = Field(ge=0, description="Tokens in the full conversation so far.")
    input_tokens: int = Field(ge=0, description="Tokens the compactor received this cycle.")
    artifact_tokens: int = Field(ge=0, description="Tokens of the rendered artifact.")
    budget_tokens: int | None = Field(default=None, ge=1)
    over_budget: bool = False
    latency_ms: int | None = None
    compactor_usage: TokenUsage | None = None
    reader_usage: TokenUsage | None = None
    control_usage: TokenUsage | None = None
    oracle_score: float | None = Field(default=None, ge=0.0, le=1.0)
    null_score: float | None = Field(default=None, ge=0.0, le=1.0)
    warnings: list[str] = Field(
        default_factory=list, description="The method's own warnings, copied off the artifact."
    )

    @property
    def compression_ratio(self) -> float:
        return self.source_tokens / max(self.artifact_tokens, 1)


class CaseResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str
    family: str
    seed: int
    cycles: list[CycleResult]
    score: float = Field(ge=0.0, le=1.0, description="Mean probe score across every cycle.")
    token_usage: TokenUsage | None = None


class FamilyMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    score: float = Field(ge=0.0, le=1.0)
    normalized_score: float | None = Field(default=None, ge=0.0, le=1.0)
    oracle_score: float | None = Field(default=None, ge=0.0, le=1.0)
    null_score: float | None = Field(default=None, ge=0.0, le=1.0)
    cases: int = Field(ge=0)
    probes: int = Field(ge=0)


class CategoryMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    score: float = Field(ge=0.0, le=1.0)
    probes: int = Field(ge=0)


class RunMetrics(BaseModel):
    """Run-level aggregates. ``score`` is the headline number."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    score: float = Field(ge=0.0, le=1.0, description="Family-balanced mean probe score.")
    score_ci_low: float = Field(ge=0.0, le=1.0)
    score_ci_high: float = Field(ge=0.0, le=1.0)
    normalized_score: float | None = Field(default=None, ge=0.0, le=1.0)
    by_family: dict[str, FamilyMetrics] = Field(default_factory=dict)
    by_category: dict[str, CategoryMetrics] = Field(default_factory=dict)
    by_cycle: list[float] = Field(default_factory=list[float])
    drift_resistance: float = Field(ge=0.0, le=1.0)
    decay: float = Field(ge=-1.0, le=1.0, description="Cycle-0 minus final-cycle score.")
    stale_rate: float = Field(ge=0.0, le=1.0)
    trap_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    hallucination_rate: float = Field(ge=0.0, le=1.0)
    compression_ratio: float = Field(ge=0.0)
    mean_artifact_tokens: float = Field(ge=0.0)
    budget_violations: int = Field(ge=0)
    reader_error_rate: float = Field(ge=0.0, le=1.0)


class RunResult(BaseModel):
    """Run metadata, every case result, and the aggregates computed from them."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str
    method_name: str
    method_version: str
    suite: str
    suite_version: str
    season: str | None = None
    difficulty: str
    drift_cycles: int = Field(ge=0)
    compactor_provider: str
    compactor_model: str
    compactor_endpoint_kind: str = "default"
    reader_provider: str
    reader_model: str
    reader_endpoint_kind: str = "default"
    reader_effort: str | None = None
    seed_group: str = "default"
    cases_per_family: int = Field(default=0, ge=0)
    budget_tokens: int | None = None
    controls: bool = False
    scorer_version: str
    started_at: datetime
    completed_at: datetime
    cases: list[CaseResult]
    metrics: RunMetrics
    token_usage: TokenUsage | None = None
    notes: list[str] = Field(default_factory=list)
