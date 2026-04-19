"""Integration tests for ``compactbench score`` CLI output."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from compactbench.cli import app
from compactbench.contracts import CaseResult, CycleResult, ItemScore, Scorecard, TokenUsage
from compactbench.runner.persistence import (
    SCORER_VERSION,
    CaseCompleteEvent,
    ResultsWriter,
    RunEndEvent,
    RunStartEvent,
)

pytestmark = pytest.mark.unit


def _scorecard_with_mixed_types() -> Scorecard:
    return Scorecard(
        cycle_number=0,
        cycle_score=0.5,
        penalized_cycle_score=0.5,
        contradiction_rate=0.0,
        compression_ratio=5.0,
        item_scores=[
            ItemScore(
                item_key="a",
                item_type="locked_decision_retention",
                score=0.0,
                weight=3.0,
                check_type="contains_normalized",
            ),
            ItemScore(
                item_key="b",
                item_type="entity_integrity",
                score=1.0,
                weight=1.0,
                check_type="contains_normalized",
            ),
        ],
    )


def _case(case_id: str) -> CaseResult:
    return CaseResult(
        case_id=case_id,
        template_key="t",
        seed=42,
        cycles=[CycleResult(cycle_number=0, scorecard=_scorecard_with_mixed_types())],
        case_score=0.5,
        drift_resistance=1.0,
    )


def _write_results(path: Path) -> None:
    now = datetime(2026, 4, 17, 10, 0, 0, tzinfo=UTC)
    with ResultsWriter(path) as writer:
        writer.write(
            RunStartEvent(
                run_id="r",
                method_name="naive-summary",
                method_version="1.0.0",
                suite_key="starter",
                suite_version="1.0.0",
                scorer_version=SCORER_VERSION,
                target_provider="mock",
                target_model="mock-det",
                difficulty="medium",
                drift_cycles=0,
                seed_group="default",
                case_count_per_template=1,
                started_at=now,
            )
        )
        writer.write(CaseCompleteEvent(case_result=_case("c1")))
        writer.write(
            RunEndEvent(
                completed_at=now,
                overall_score=0.5,
                drift_resistance=1.0,
                constraint_retention=1.0,
                contradiction_rate=0.0,
                compression_ratio=5.0,
            )
        )


def test_score_command_prints_item_type_breakdown_table(tmp_path: Path) -> None:
    path = tmp_path / "results.jsonl"
    _write_results(path)

    runner = CliRunner()
    result = runner.invoke(app, ["score", "--results", str(path)])

    assert result.exit_code == 0, result.stdout
    assert "Failures by item type" in result.stdout
    assert "locked_decision_retention" in result.stdout
    assert "entity_integrity" in result.stdout
    idx_bad = result.stdout.index("locked_decision_retention")
    idx_good = result.stdout.index("entity_integrity")
    assert idx_bad < idx_good, "worst mean_score should appear first"


def test_score_command_prints_token_usage_table_when_populated(tmp_path: Path) -> None:
    path = tmp_path / "results.jsonl"
    now = datetime(2026, 4, 17, 10, 0, 0, tzinfo=UTC)
    usage = TokenUsage(
        prompt_tokens=1234, completion_tokens=567, cached_prompt_tokens=800, call_count=12
    )
    case = CaseResult(
        case_id="c1",
        template_key="t",
        seed=42,
        cycles=[
            CycleResult(
                cycle_number=0,
                scorecard=_scorecard_with_mixed_types(),
                token_usage=usage,
            )
        ],
        case_score=0.5,
        drift_resistance=1.0,
        token_usage=usage,
    )
    with ResultsWriter(path) as writer:
        writer.write(
            RunStartEvent(
                run_id="r",
                method_name="m",
                method_version="1.0.0",
                suite_key="starter",
                suite_version="1.0.0",
                scorer_version=SCORER_VERSION,
                target_provider="mock",
                target_model="mock-det",
                difficulty="medium",
                drift_cycles=0,
                seed_group="default",
                case_count_per_template=1,
                started_at=now,
            )
        )
        writer.write(CaseCompleteEvent(case_result=case))
        writer.write(
            RunEndEvent(
                completed_at=now,
                overall_score=0.5,
                drift_resistance=1.0,
                constraint_retention=1.0,
                contradiction_rate=0.0,
                compression_ratio=5.0,
                token_usage=usage,
            )
        )

    runner = CliRunner()
    result = runner.invoke(app, ["score", "--results", str(path)])

    assert result.exit_code == 0, result.stdout
    assert "Token usage" in result.stdout
    assert "prompt_tokens" in result.stdout
    assert "completion_tokens" in result.stdout
    assert "total_tokens" in result.stdout
    assert "1,234" in result.stdout or "1234" in result.stdout
    assert "prompt_cache_hit_rate" in result.stdout


def test_score_command_omits_token_table_when_token_usage_is_missing(tmp_path: Path) -> None:
    path = tmp_path / "results.jsonl"
    _write_results(path)  # _write_results leaves token_usage unset

    runner = CliRunner()
    result = runner.invoke(app, ["score", "--results", str(path)])

    assert result.exit_code == 0, result.stdout
    assert "Token usage" not in result.stdout


def test_score_command_omits_breakdown_when_no_item_scores(tmp_path: Path) -> None:
    path = tmp_path / "results.jsonl"
    now = datetime(2026, 4, 17, 10, 0, 0, tzinfo=UTC)
    empty_case = CaseResult(
        case_id="c1",
        template_key="t",
        seed=42,
        cycles=[
            CycleResult(
                cycle_number=0,
                scorecard=Scorecard(
                    cycle_number=0,
                    cycle_score=0.0,
                    penalized_cycle_score=0.0,
                    contradiction_rate=0.0,
                    compression_ratio=1.0,
                    item_scores=[],
                ),
            )
        ],
        case_score=0.0,
        drift_resistance=1.0,
    )
    with ResultsWriter(path) as writer:
        writer.write(
            RunStartEvent(
                run_id="r",
                method_name="m",
                method_version="1.0.0",
                suite_key="starter",
                suite_version="1.0.0",
                scorer_version=SCORER_VERSION,
                target_provider="mock",
                target_model="mock-det",
                difficulty="medium",
                drift_cycles=0,
                seed_group="default",
                case_count_per_template=1,
                started_at=now,
            )
        )
        writer.write(CaseCompleteEvent(case_result=empty_case))

    runner = CliRunner()
    result = runner.invoke(app, ["score", "--results", str(path)])

    assert result.exit_code == 0, result.stdout
    assert "Failures by item type" not in result.stdout
