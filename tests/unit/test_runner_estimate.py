"""Tests for the ``--estimate`` flag's projection logic."""

from __future__ import annotations

from pathlib import Path

import pytest

from compactbench.dsl import (
    DifficultyLevel,
    TemplateDefinition,
    load_suite,
    validate_template,
)
from compactbench.runner.costs import (
    MODEL_COSTS,
    dollars,
    free_tier_daily_limit,
    lookup_cost,
)
from compactbench.runner.estimate import (
    EstimateResult,
    estimate_run,
    format_estimate,
)

pytestmark = pytest.mark.unit


_STARTER_DIR = Path(__file__).resolve().parents[2] / "benchmarks" / "public" / "starter"


def _load_starter() -> list[TemplateDefinition]:
    templates = load_suite(_STARTER_DIR)
    for t in templates:
        validate_template(t)
    return templates


class TestCostCatalog:
    def test_lookup_known_pair_returns_cost(self) -> None:
        cost = lookup_cost("groq", "llama-3.3-70b-versatile")
        assert cost is not None
        assert cost.input_per_mtok > 0
        assert cost.output_per_mtok > 0

    def test_lookup_unknown_pair_returns_none(self) -> None:
        assert lookup_cost("groq", "nonexistent-model") is None
        assert lookup_cost("no-such-provider", "gpt-4o") is None

    def test_ollama_models_are_free(self) -> None:
        cost = lookup_cost("ollama", "llama3.2")
        assert cost is not None
        assert cost.input_per_mtok == 0.0
        assert cost.output_per_mtok == 0.0

    def test_dollars_matches_hand_math(self) -> None:
        # $0.59 / M input + $0.79 / M output
        cost = MODEL_COSTS[("groq", "llama-3.3-70b-versatile")]
        total = dollars(cost, input_tokens=2_000_000, output_tokens=1_000_000)
        assert total == pytest.approx(2 * 0.59 + 1 * 0.79)

    def test_free_tier_lookup_returns_cap_for_groq(self) -> None:
        assert free_tier_daily_limit("groq", "llama-3.3-70b-versatile") == 100_000

    def test_free_tier_returns_none_for_unlimited_providers(self) -> None:
        assert free_tier_daily_limit("openai", "gpt-4o-mini") is None


class TestEstimateRun:
    def test_basic_shape(self) -> None:
        templates = _load_starter()
        est = estimate_run(
            templates=templates,
            suite_key="starter",
            suite_version="1.0.0",
            seed_group="default",
            case_count_per_template=1,
            difficulty=DifficultyLevel.MEDIUM,
            drift_cycles=0,
            provider_key="groq",
            model="llama-3.3-70b-versatile",
        )
        assert est.total_cases == len(templates)  # 1 case per template with case_count=1
        assert est.total_calls > 0
        assert est.input_tokens > 0
        assert est.output_tokens > 0
        assert est.cost_usd is not None
        assert est.cost_usd > 0
        assert est.daily_limit == 100_000

    def test_case_count_scales_linearly(self) -> None:
        """Doubling case-count should roughly double totals — a smoke check on the math."""
        templates = _load_starter()
        one = estimate_run(
            templates=templates,
            suite_key="starter",
            suite_version="1.0.0",
            seed_group="default",
            case_count_per_template=1,
            difficulty=DifficultyLevel.MEDIUM,
            drift_cycles=0,
            provider_key="mock",
            model="mock-model",
        )
        four = estimate_run(
            templates=templates,
            suite_key="starter",
            suite_version="1.0.0",
            seed_group="default",
            case_count_per_template=4,
            difficulty=DifficultyLevel.MEDIUM,
            drift_cycles=0,
            provider_key="mock",
            model="mock-model",
        )

        assert four.total_cases == 4 * one.total_cases
        assert four.total_calls == 4 * one.total_calls

    def test_drift_cycles_multiply_calls(self) -> None:
        """With drift_cycles=N, each case runs N+1 cycles -> proportional call count."""
        templates = _load_starter()
        one = estimate_run(
            templates=templates,
            suite_key="starter",
            suite_version="1.0.0",
            seed_group="default",
            case_count_per_template=1,
            difficulty=DifficultyLevel.MEDIUM,
            drift_cycles=0,  # 1 cycle per case
            provider_key="mock",
            model="mock-model",
        )
        three = estimate_run(
            templates=templates,
            suite_key="starter",
            suite_version="1.0.0",
            seed_group="default",
            case_count_per_template=1,
            difficulty=DifficultyLevel.MEDIUM,
            drift_cycles=2,  # 3 cycles per case
            provider_key="mock",
            model="mock-model",
        )

        assert three.total_calls == 3 * one.total_calls

    def test_unknown_model_returns_none_cost(self) -> None:
        templates = _load_starter()
        est = estimate_run(
            templates=templates,
            suite_key="starter",
            suite_version="1.0.0",
            seed_group="default",
            case_count_per_template=1,
            difficulty=DifficultyLevel.MEDIUM,
            drift_cycles=0,
            provider_key="groq",
            model="nonexistent-model",
        )
        assert est.cost_usd is None


class TestFormatEstimate:
    def _sample(self, *, cost: float | None = 1.23, limit: int | None = 100_000) -> EstimateResult:
        return EstimateResult(
            total_cases=15,
            total_calls=60,
            input_tokens=1_000_000,
            output_tokens=100_000,
            cost_usd=cost,
            daily_limit=limit,
            provider_key="groq",
            model="llama-3.3-70b-versatile",
        )

    def test_includes_all_sections_when_cost_and_limit_known(self) -> None:
        report = format_estimate(self._sample())
        assert "Run plan" in report
        assert "cases total:     15" in report
        assert "API calls:       60" in report
        assert "Cost on groq / llama-3.3-70b-versatile" in report
        assert "$1.23" in report
        assert "Free-tier check" in report

    def test_warns_when_run_exceeds_free_tier(self) -> None:
        """1.1M tokens vs 100k cap should flag the run as over-budget."""
        report = format_estimate(self._sample(limit=100_000))
        assert "exceed" in report
        assert "11.0x" in report  # 1.1M total / 100k cap

    def test_reports_fit_when_under_cap(self) -> None:
        est = EstimateResult(
            total_cases=1,
            total_calls=3,
            input_tokens=5_000,
            output_tokens=500,
            cost_usd=0.01,
            daily_limit=100_000,
            provider_key="groq",
            model="llama-3.3-70b-versatile",
        )
        report = format_estimate(est)
        assert "fits within" in report

    def test_missing_cost_suggests_catalogue_update(self) -> None:
        report = format_estimate(self._sample(cost=None))
        assert "no cost catalogue entry" in report
        assert "src/compactbench/runner/costs.py" in report

    def test_no_free_tier_section_when_limit_unknown(self) -> None:
        report = format_estimate(self._sample(limit=None))
        assert "Free-tier check" not in report
