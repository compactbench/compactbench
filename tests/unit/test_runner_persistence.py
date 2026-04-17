"""Results JSONL writer/reader tests."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from compactbench.contracts import (
    CaseResult,
    CycleResult,
    ItemScore,
    Scorecard,
)
from compactbench.runner.persistence import (
    SCORER_VERSION,
    CaseCompleteEvent,
    ResultsWriter,
    RunEndEvent,
    RunStartEvent,
    aggregate_run_metrics,
    completed_case_ids,
    iter_events,
    read_run_start,
    to_run_result,
)

pytestmark = pytest.mark.unit


def _scorecard(
    *,
    cycle_number: int = 0,
    cycle_score: float = 0.9,
    contradiction_rate: float = 0.0,
    compression_ratio: float = 5.0,
) -> Scorecard:
    return Scorecard(
        cycle_number=cycle_number,
        cycle_score=cycle_score,
        penalized_cycle_score=cycle_score * (1.0 - contradiction_rate),
        contradiction_rate=contradiction_rate,
        compression_ratio=compression_ratio,
        item_scores=[
            ItemScore(
                item_key="q1",
                item_type="locked_decision_retention",
                score=cycle_score,
                weight=3.0,
                check_type="contains_normalized",
            ),
        ],
    )


def _case_result(case_id: str, *, n_cycles: int = 2) -> CaseResult:
    cycles = [
        CycleResult(cycle_number=i, scorecard=_scorecard(cycle_number=i)) for i in range(n_cycles)
    ]
    return CaseResult(
        case_id=case_id,
        template_key="buried_constraint_starter_v1",
        seed=42 + int(case_id[-1]) if case_id[-1].isdigit() else 42,
        cycles=cycles,
        case_score=sum(c.scorecard.penalized_cycle_score for c in cycles) / len(cycles),
        drift_resistance=1.0,
    )


def _run_start_event() -> RunStartEvent:
    return RunStartEvent(
        run_id="run-1",
        method_name="naive-summary",
        method_version="1.0.0",
        suite_key="starter",
        suite_version="1.0.0",
        scorer_version=SCORER_VERSION,
        target_provider="mock",
        target_model="mock-deterministic",
        difficulty="medium",
        drift_cycles=1,
        seed_group="default",
        case_count_per_template=1,
        started_at=datetime(2026, 4, 17, 10, 0, 0, tzinfo=UTC),
    )


def test_write_and_read_event_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "results.jsonl"
    with ResultsWriter(path) as writer:
        writer.write(_run_start_event())
        writer.write(CaseCompleteEvent(case_result=_case_result("case-0")))
        writer.write(CaseCompleteEvent(case_result=_case_result("case-1")))
        writer.write(
            RunEndEvent(
                completed_at=datetime(2026, 4, 17, 10, 5, 0, tzinfo=UTC),
                overall_score=0.8,
                drift_resistance=0.95,
                constraint_retention=0.9,
                contradiction_rate=0.05,
                compression_ratio=7.5,
            )
        )

    events = list(iter_events(path))
    assert len(events) == 4
    assert isinstance(events[0], RunStartEvent)
    assert isinstance(events[1], CaseCompleteEvent)
    assert isinstance(events[3], RunEndEvent)


def test_completed_case_ids_reads_streamed_cases(tmp_path: Path) -> None:
    path = tmp_path / "results.jsonl"
    with ResultsWriter(path) as writer:
        writer.write(_run_start_event())
        writer.write(CaseCompleteEvent(case_result=_case_result("case-a")))
        writer.write(CaseCompleteEvent(case_result=_case_result("case-b")))
    assert completed_case_ids(path) == {"case-a", "case-b"}


def test_completed_case_ids_empty_when_file_missing(tmp_path: Path) -> None:
    assert completed_case_ids(tmp_path / "nope.jsonl") == set()


def test_read_run_start(tmp_path: Path) -> None:
    path = tmp_path / "results.jsonl"
    with ResultsWriter(path) as writer:
        writer.write(_run_start_event())
    start = read_run_start(path)
    assert start is not None
    assert start.run_id == "run-1"


def test_read_run_start_returns_none_when_no_start(tmp_path: Path) -> None:
    path = tmp_path / "empty.jsonl"
    path.write_text("", encoding="utf-8")
    assert read_run_start(path) is None


def test_to_run_result_uses_run_end_when_present(tmp_path: Path) -> None:
    path = tmp_path / "results.jsonl"
    with ResultsWriter(path) as writer:
        writer.write(_run_start_event())
        writer.write(CaseCompleteEvent(case_result=_case_result("c1")))
        writer.write(
            RunEndEvent(
                completed_at=datetime(2026, 4, 17, 10, 5, 0, tzinfo=UTC),
                overall_score=0.8,
                drift_resistance=0.9,
                constraint_retention=0.75,
                contradiction_rate=0.05,
                compression_ratio=5.0,
            )
        )
    run_result = to_run_result(path)
    assert run_result.overall_score == 0.8
    assert run_result.drift_resistance == 0.9
    assert run_result.notes == []


def test_to_run_result_falls_back_to_cases_when_run_end_missing(tmp_path: Path) -> None:
    path = tmp_path / "results.jsonl"
    with ResultsWriter(path) as writer:
        writer.write(_run_start_event())
        writer.write(CaseCompleteEvent(case_result=_case_result("c1")))
    run_result = to_run_result(path)
    assert run_result.notes  # has the "incomplete" note
    assert any("incomplete" in n for n in run_result.notes)
    assert len(run_result.cases) == 1


def test_to_run_result_raises_without_run_start(tmp_path: Path) -> None:
    path = tmp_path / "empty.jsonl"
    path.write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="no run_start"):
        to_run_result(path)


def test_aggregate_with_empty_list() -> None:
    metrics = aggregate_run_metrics([])
    assert metrics["overall_score"] == 0.0
    assert metrics["drift_resistance"] == 1.0


def test_aggregate_computes_means() -> None:
    cr1 = _case_result("c1")
    cr2 = _case_result("c2")
    metrics = aggregate_run_metrics([cr1, cr2])
    assert 0.0 <= metrics["overall_score"] <= 1.0
    assert 0.0 <= metrics["drift_resistance"] <= 1.0
    assert metrics["constraint_retention"] > 0.0  # both have locked_decision_retention items


def test_writer_creates_parent_directories(tmp_path: Path) -> None:
    nested = tmp_path / "deep" / "nested" / "results.jsonl"
    with ResultsWriter(nested) as writer:
        writer.write(_run_start_event())
    assert nested.exists()


def test_writer_append_mode_preserves_existing(tmp_path: Path) -> None:
    path = tmp_path / "results.jsonl"
    with ResultsWriter(path) as writer:
        writer.write(_run_start_event())
        writer.write(CaseCompleteEvent(case_result=_case_result("c1")))
    with ResultsWriter(path, mode="append") as writer:
        writer.write(CaseCompleteEvent(case_result=_case_result("c2")))
    assert completed_case_ids(path) == {"c1", "c2"}
