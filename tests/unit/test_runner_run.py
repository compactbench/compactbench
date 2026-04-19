"""End-to-end run orchestrator tests using the mock provider."""

from __future__ import annotations

from pathlib import Path

import pytest

from compactbench.dsl import DifficultyLevel
from compactbench.runner import (
    ResumeError,
    RunArgs,
    RunnerError,
    completed_case_ids,
    run_experiment,
    to_run_result,
)

pytestmark = pytest.mark.unit


_STARTER_DIR = Path(__file__).resolve().parents[2] / "benchmarks" / "public"


def _args(
    output: Path,
    *,
    case_count: int = 1,
    drift_cycles: int = 0,
    resume: bool = False,
    method: str = "built-in:naive-summary",
) -> RunArgs:
    return RunArgs(
        method_spec=method,
        suite_key="starter",
        provider_key="mock",
        model="mock-m",
        difficulty=DifficultyLevel.MEDIUM,
        drift_cycles=drift_cycles,
        case_count_per_template=case_count,
        seed_group="default",
        benchmarks_dir=_STARTER_DIR,
        output_path=output,
        resume=resume,
    )


async def test_end_to_end_starter_suite_one_cycle(tmp_path: Path) -> None:
    output = tmp_path / "results.jsonl"
    await run_experiment(_args(output, case_count=1, drift_cycles=0))

    run_result = to_run_result(output)
    # Starter has 4 templates with 1 case each = 4 cases.
    assert len(run_result.cases) == 4
    assert run_result.method_name == "naive-summary"
    assert run_result.suite_key == "starter"
    # Every case has 1 cycle.
    for case in run_result.cases:
        assert len(case.cycles) == 1


async def test_end_to_end_with_drift_cycles(tmp_path: Path) -> None:
    output = tmp_path / "results.jsonl"
    await run_experiment(_args(output, case_count=1, drift_cycles=2))

    run_result = to_run_result(output)
    for case in run_result.cases:
        assert len(case.cycles) == 3  # cycle 0 + 2 drift cycles
        assert case.cycles[0].drift_delta is None
        # Later cycles should have drift_delta set (could be 0 if scores flat).
        for c in case.cycles[1:]:
            assert c.drift_delta is not None


async def test_writes_run_start_case_complete_run_end(tmp_path: Path) -> None:
    from compactbench.runner import iter_events
    from compactbench.runner.persistence import (
        CaseCompleteEvent,
        RunEndEvent,
        RunStartEvent,
    )

    output = tmp_path / "results.jsonl"
    await run_experiment(_args(output, case_count=1, drift_cycles=0))

    events = list(iter_events(output))
    assert isinstance(events[0], RunStartEvent)
    assert isinstance(events[-1], RunEndEvent)
    case_events = [e for e in events if isinstance(e, CaseCompleteEvent)]
    assert len(case_events) == 4


async def test_respects_case_count_per_template(tmp_path: Path) -> None:
    output = tmp_path / "results.jsonl"
    await run_experiment(_args(output, case_count=2, drift_cycles=0))

    run_result = to_run_result(output)
    # 4 templates with 2 cases each = 8 cases.
    assert len(run_result.cases) == 8


async def test_raises_on_unknown_suite(tmp_path: Path) -> None:
    bad = RunArgs(
        method_spec="built-in:naive-summary",
        suite_key="not-a-real-suite",
        provider_key="mock",
        model="m",
        difficulty=DifficultyLevel.MEDIUM,
        drift_cycles=0,
        case_count_per_template=1,
        seed_group="default",
        benchmarks_dir=_STARTER_DIR,
        output_path=tmp_path / "results.jsonl",
        resume=False,
    )
    with pytest.raises(RunnerError, match="suite directory"):
        await run_experiment(bad)


async def test_resume_skips_completed_cases(tmp_path: Path) -> None:
    output = tmp_path / "results.jsonl"
    # First run completes fully.
    await run_experiment(_args(output, case_count=1, drift_cycles=0))
    first_completed = completed_case_ids(output)
    assert len(first_completed) == 4

    # Resume run should produce the same set of completed cases (no-op continuation).
    await run_experiment(_args(output, case_count=1, drift_cycles=0, resume=True))
    assert completed_case_ids(output) == first_completed


async def test_resume_rejects_incompatible_args(tmp_path: Path) -> None:
    output = tmp_path / "results.jsonl"
    await run_experiment(_args(output, case_count=1, drift_cycles=0))

    # Change method — should reject resume.
    incompatible = _args(
        output, case_count=1, drift_cycles=0, resume=True, method="built-in:hybrid-ledger"
    )
    with pytest.raises(ResumeError, match="method_name"):
        await run_experiment(incompatible)


async def test_end_to_end_deterministic(tmp_path: Path) -> None:
    output_a = tmp_path / "a.jsonl"
    output_b = tmp_path / "b.jsonl"
    await run_experiment(_args(output_a, case_count=1, drift_cycles=0))
    await run_experiment(_args(output_b, case_count=1, drift_cycles=0))

    result_a = to_run_result(output_a)
    result_b = to_run_result(output_b)
    # Same case IDs, same cycle scores (mock provider is deterministic).
    # Sorted compare: concurrency can re-order completion events but the
    # set and per-case scores must still match exactly.
    by_id_a = {c.case_id: c for c in result_a.cases}
    by_id_b = {c.case_id: c for c in result_b.cases}
    assert set(by_id_a) == set(by_id_b)
    for cid in by_id_a:
        assert by_id_a[cid].case_score == by_id_b[cid].case_score


async def test_concurrency_default_matches_serial(tmp_path: Path) -> None:
    """Parallel execution must produce the same per-case results as serial."""
    output_serial = tmp_path / "serial.jsonl"
    output_parallel = tmp_path / "parallel.jsonl"

    serial_args = _args(output_serial, case_count=2, drift_cycles=1)
    from dataclasses import replace

    await run_experiment(replace(serial_args, concurrency=1))
    await run_experiment(replace(serial_args, output_path=output_parallel, concurrency=4))

    serial = to_run_result(output_serial)
    parallel = to_run_result(output_parallel)
    assert {c.case_id for c in serial.cases} == {c.case_id for c in parallel.cases}

    serial_by_id = {c.case_id: c.case_score for c in serial.cases}
    parallel_by_id = {c.case_id: c.case_score for c in parallel.cases}
    assert serial_by_id == parallel_by_id


async def test_concurrency_defaults_to_four() -> None:
    """Sanity: the public RunArgs default matches the CLI default."""
    args = RunArgs(
        method_spec="built-in:naive-summary",
        suite_key="starter",
        provider_key="mock",
        model="m",
        difficulty=DifficultyLevel.MEDIUM,
        drift_cycles=0,
        case_count_per_template=1,
        seed_group="default",
        benchmarks_dir=_STARTER_DIR,
        output_path=Path("results.jsonl"),
        resume=False,
    )
    assert args.concurrency == 4


async def test_concurrency_semaphore_caps_active_tasks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Concurrency cap is honoured: the compactor never sees more than N in flight."""
    import asyncio as _asyncio
    from dataclasses import replace
    from typing import Any, ClassVar

    from compactbench import compactors as _compactors_module
    from compactbench.compactors import Compactor
    from compactbench.contracts import CompactionArtifact, StructuredState, Transcript

    max_concurrent = 0
    in_flight = 0
    lock = _asyncio.Lock()

    class CountingCompactor(Compactor):
        """Records the peak in-flight count during compact() calls."""

        name: ClassVar[str] = "smoke-counting"
        version: ClassVar[str] = "0.0.1"

        async def compact(
            self,
            transcript: Transcript,
            config: dict[str, Any] | None = None,
            previous_artifact: CompactionArtifact | None = None,
        ) -> CompactionArtifact:
            nonlocal in_flight, max_concurrent
            async with lock:
                in_flight += 1
                max_concurrent = max(max_concurrent, in_flight)
            await _asyncio.sleep(0.02)  # hold the slot long enough to observe concurrency
            async with lock:
                in_flight -= 1
            return CompactionArtifact(
                summaryText="x",
                structured_state=StructuredState(),
                selectedSourceTurnIds=[t.id for t in transcript.turns],
                warnings=[],
                methodMetadata={"method": self.name, "version": self.version},
            )

    monkeypatch.setitem(
        _compactors_module._BUILT_IN,  # pyright: ignore[reportPrivateUsage]
        "smoke-counting",
        CountingCompactor,
    )

    output = tmp_path / "sem.jsonl"
    base = _args(output, case_count=3, drift_cycles=0, method="built-in:smoke-counting")
    await run_experiment(replace(base, concurrency=2))

    # 3 templates x 3 cases = 9 tasks; with concurrency=2 the peak must be <= 2.
    assert max_concurrent <= 2
    # And we should have actually reached the cap at least once in a real parallel run.
    assert max_concurrent >= 2
