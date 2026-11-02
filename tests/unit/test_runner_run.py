"""End-to-end runs with an offline method provider and an answer-key reader."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from compactbench.providers import MockProvider
from compactbench.runner import (
    ResumeError,
    RunArgs,
    RunnerError,
    completed_case_ids,
    read_run_start,
    run_experiment,
    to_run_result,
)
from compactbench.scenarios import expand_suite, get_suite
from tests.helpers import AnswerKeyReader

pytestmark = pytest.mark.unit


def _args(output: Path, **overrides: object) -> RunArgs:
    fields: dict[str, object] = {
        "method_spec": "built-in:oracle",
        "suite": "starter",
        "provider_key": "mock",
        "model": "m",
        "reader_model": "reader-m",
        "output_path": output,
        "cases_per_family": 1,
        "concurrency": 1,
    }
    fields.update(overrides)
    return RunArgs(**fields)  # type: ignore[arg-type]


def _reader(**kw: bool) -> AnswerKeyReader:
    return AnswerKeyReader(expand_suite(get_suite("starter"), cases_per_family=1), **kw)


async def test_oracle_scores_full_marks(tmp_path: Path) -> None:
    out = tmp_path / "r.jsonl"
    await run_experiment(_args(out), provider=MockProvider(), reader_provider=_reader())
    result = to_run_result(out)
    assert result.metrics.score == 1.0
    assert result.metrics.drift_resistance == 1.0
    assert result.reader_model == "reader-m"
    assert result.budget_tokens == 2048
    assert all(c.budget_tokens is None for case in result.cases for c in case.cycles)


async def test_null_method_scores_nothing(tmp_path: Path) -> None:
    # Its only right answers are abstentions, which earn nothing.
    out = tmp_path / "r.jsonl"
    await run_experiment(
        _args(out, method_spec="built-in:null"),
        provider=MockProvider(),
        reader_provider=_reader(know_nothing=True),
    )
    metrics = to_run_result(out).metrics
    assert metrics.score == 0.0
    assert metrics.hallucination_rate == 0.0
    assert metrics.drift_resistance == 0.0


async def test_results_file_holds_no_case_content(tmp_path: Path) -> None:
    out = tmp_path / "r.jsonl"
    await run_experiment(_args(out), provider=MockProvider(), reader_provider=_reader())
    text = out.read_text(encoding="utf-8")
    case = expand_suite(get_suite("starter"), cases_per_family=1)[0]
    assert case.cycles[0].probes[0].question not in text
    assert case.cycles[0].turns[0].content not in text


async def test_traces_hold_everything(tmp_path: Path) -> None:
    out = tmp_path / "r.jsonl"
    traces = tmp_path / "t.jsonl"
    await run_experiment(
        _args(out, traces_path=traces), provider=MockProvider(), reader_provider=_reader()
    )
    records = [json.loads(line) for line in traces.read_text(encoding="utf-8").splitlines()]
    assert records
    assert {"artifact", "probes", "answers", "reader_responses", "result"} <= set(records[0])


async def test_resume_skips_completed_cases(tmp_path: Path) -> None:
    out = tmp_path / "r.jsonl"
    await run_experiment(_args(out), provider=MockProvider(), reader_provider=_reader())
    done = completed_case_ids(out)
    start = read_run_start(out)
    reader = _reader()
    await run_experiment(_args(out, resume=True), provider=MockProvider(), reader_provider=reader)
    assert reader.calls == 0
    assert completed_case_ids(out) == done
    resumed = read_run_start(out)
    assert start is not None
    assert resumed is not None
    assert resumed.run_id == start.run_id


async def test_resume_refuses_different_settings(tmp_path: Path) -> None:
    out = tmp_path / "r.jsonl"
    await run_experiment(_args(out), provider=MockProvider(), reader_provider=_reader())
    with pytest.raises(ResumeError, match="budget_tokens"):
        await run_experiment(
            _args(out, resume=True, budget_tokens=1024),
            provider=MockProvider(),
            reader_provider=_reader(),
        )


async def test_unknown_suite(tmp_path: Path) -> None:
    with pytest.raises(RunnerError, match="unknown suite"):
        await run_experiment(_args(tmp_path / "r.jsonl", suite="nope"))


async def test_built_in_method_runs_through_every_cycle(tmp_path: Path) -> None:
    out = tmp_path / "r.jsonl"
    await run_experiment(
        _args(out, method_spec="built-in:naive-summary", drift_cycles=1),
        provider=MockProvider(default="a summary"),
        reader_provider=_reader(),
    )
    result = to_run_result(out)
    assert result.drift_cycles == 1
    assert all(len(case.cycles) == 2 for case in result.cases)
    assert result.token_usage is not None
