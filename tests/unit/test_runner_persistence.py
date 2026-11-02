"""Results file: event log round-trip, recomputed aggregates, partial files."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from compactbench.contracts import CaseResult, CycleResult, ProbeResult
from compactbench.runner import (
    INCOMPLETE_RUN_NOTE,
    CaseCompleteEvent,
    ResultsWriter,
    RunEndEvent,
    RunStartEvent,
    iter_events,
    to_run_result,
)
from compactbench.scoring import compute_metrics

pytestmark = pytest.mark.unit


def _start() -> RunStartEvent:
    return RunStartEvent(
        run_id="r",
        method_name="m",
        method_version="1",
        suite="starter",
        suite_version="2.0.0",
        difficulty="easy",
        drift_cycles=1,
        cases_per_family=1,
        seed_group="default",
        compactor_provider="mock",
        compactor_model="m",
        reader_provider="mock",
        reader_model="m",
        budget_tokens=512,
        scorer_version="3.0.0",
        started_at=datetime(2026, 11, 1, tzinfo=UTC),
    )


def _case(score: float) -> CaseResult:
    probe = ProbeResult(
        key="k", category="fact_recall", format="value", origin_cycle=0, score=score, answered=True
    )
    cycle = CycleResult(
        cycle=0,
        score=score,
        probe_results=[probe],
        source_tokens=100,
        input_tokens=100,
        artifact_tokens=10,
    )
    return CaseResult(case_id=f"c{score}", family="f", seed=1, cycles=[cycle], score=score)


def test_round_trip_recomputes_aggregates(tmp_path: Path) -> None:
    out = tmp_path / "r.jsonl"
    cases = [_case(1.0), _case(0.0)]
    with ResultsWriter(out) as writer:
        writer.write(_start())
        for case in cases:
            writer.write(CaseCompleteEvent(case_result=case))
        tampered = compute_metrics([_case(1.0)])
        writer.write(RunEndEvent(completed_at=datetime.now(UTC), metrics=tampered))
    result = to_run_result(out)
    assert result.metrics.score == pytest.approx(0.5), "aggregates come from the cases"
    assert result.notes == []


def test_missing_run_end_marks_incomplete(tmp_path: Path) -> None:
    out = tmp_path / "r.jsonl"
    with ResultsWriter(out) as writer:
        writer.write(_start())
        writer.write(CaseCompleteEvent(case_result=_case(1.0)))
    assert INCOMPLETE_RUN_NOTE in to_run_result(out).notes


def test_truncated_final_line_is_tolerated(tmp_path: Path) -> None:
    out = tmp_path / "r.jsonl"
    with ResultsWriter(out) as writer:
        writer.write(_start())
    with out.open("a", encoding="utf-8") as fp:
        fp.write('{"event": "case_comp')
    assert len(list(iter_events(out))) == 1


def test_corruption_mid_file_raises(tmp_path: Path) -> None:
    out = tmp_path / "r.jsonl"
    out.write_text('{"nope": 1}\n' + _start().model_dump_json() + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid event"):
        to_run_result(out)


def test_v1_results_file_gets_a_clear_error(tmp_path: Path) -> None:
    out = tmp_path / "r.jsonl"
    out.write_text(
        '{"event": "run_start", "run_id": "x", "target_model": "old"}\n', encoding="utf-8"
    )
    with pytest.raises(ValueError, match=r"0\.2 and earlier"):
        to_run_result(out)
