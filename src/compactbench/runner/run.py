"""Top-level run orchestrator.

Expands a suite into cases, runs every case through all of its cycles, scores
everything, and writes a streamed ``results.jsonl`` event log (plus an
optional private traces file).
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from statistics import fmean
from typing import Any

from compactbench.compactors import Compactor, OracleCompactor
from compactbench.contracts import (
    CaseResult,
    CompactionArtifact,
    CycleResult,
    GeneratedCase,
    add_usage,
)
from compactbench.providers import CountingProvider, Provider, ReasoningEffort, get_provider_cls
from compactbench.runner._resolver import resolve_compactor_class
from compactbench.runner.cycle import execute_cycle
from compactbench.runner.errors import ResumeError, RunnerError
from compactbench.runner.persistence import (
    SCORER_VERSION,
    CaseCompleteEvent,
    ResultsWriter,
    RunEndEvent,
    RunStartEvent,
    completed_case_ids,
    iter_events,
    read_run_start,
    sum_case_token_usage,
)
from compactbench.runner.reader import DEFAULT_CHUNK_SIZE
from compactbench.runner.traces import TraceWriter
from compactbench.sandbox import Sandbox, SandboxedCompactor, SandboxError, usage_counter
from compactbench.scenarios import Difficulty, expand_suite, get_suite
from compactbench.scoring.answers import counted
from compactbench.scoring.metrics import compute_metrics

DEFAULT_BUDGET_TOKENS = 2048


@dataclass(frozen=True)
class RunArgs:
    method_spec: str
    suite: str
    provider_key: str
    model: str
    output_path: Path
    reader_provider_key: str | None = None
    """Defaults to the compactor's provider."""
    reader_model: str | None = None
    """Defaults to the compactor's model."""
    reader_effort: ReasoningEffort | None = None
    """Reasoning effort for the reader, where the provider supports it."""
    difficulty: Difficulty | None = None
    drift_cycles: int | None = None
    cases_per_family: int | None = None
    seed_group: str = "default"
    budget_tokens: int | None = DEFAULT_BUDGET_TOKENS
    controls: bool = False
    traces_path: Path | None = None
    resume: bool = False
    # Maximum number of cases evaluated concurrently. 1 reproduces strictly
    # serial behaviour; higher values parallelise the I/O-bound provider calls.
    concurrency: int = 4
    season: str | None = None
    method_config: dict[str, Any] = field(default_factory=dict[str, Any])
    chunk_size: int = DEFAULT_CHUNK_SIZE
    sandbox: Sandbox | None = None
    """Run the method in this sandbox instead of importing it (ranked evaluation)."""
    sandbox_endpoint_kind: str = "default"
    """Where the sandboxed method's model calls went: the proxy forwards to providers'
    own endpoints (``"default"``) or to the submitter's own (``"custom"``)."""
    declared_method: tuple[str, str] | None = None
    """Sandbox mode: the name and version the submission declared. The run is recorded
    under them rather than whatever the method's class reports about itself."""

    @property
    def resolved_reader_provider(self) -> str:
        return self.reader_provider_key or self.provider_key

    @property
    def resolved_reader_model(self) -> str:
        return self.reader_model or self.model


async def run_experiment(
    args: RunArgs,
    *,
    provider: Provider | None = None,
    reader_provider: Provider | None = None,
) -> Path:
    """Execute a full run per ``args`` and return the path to the results file.

    ``provider`` / ``reader_provider`` override the instances built from the
    provider keys (used by tests and by harnesses that route calls through a proxy).
    """
    try:
        suite = get_suite(args.suite)
    except KeyError as exc:
        raise RunnerError(str(exc)) from exc
    cases = expand_suite(
        suite,
        seed_group=args.seed_group,
        cases_per_family=args.cases_per_family,
        difficulty=args.difficulty,
        drift_cycles=args.drift_cycles,
    )
    if not cases:
        raise RunnerError(f"suite {args.suite!r} produced no cases")

    compactor_cls: type[Compactor] | None = None
    compactor_base: Provider | None = None
    if args.sandbox is not None:
        # Submitted code is never imported here: ask the sandbox who it is, and
        # let it make its own model calls through the proxy.
        probe = SandboxedCompactor(
            args.sandbox,
            method_spec=args.method_spec,
            provider_key=args.provider_key,
            model=args.model,
            config=args.method_config,
        )
        try:
            hello = await probe.start()
        except SandboxError as exc:
            raise RunnerError(f"sandbox failed to start: {exc}") from exc
        finally:
            await probe.aclose()
        method_name, method_version = args.declared_method or (hello.name, hello.version)
        compactor_endpoint_kind = args.sandbox_endpoint_kind
    else:
        compactor_cls = resolve_compactor_class(args.method_spec)
        compactor_base = provider or _instantiate_provider(args.provider_key)
        method_name, method_version = compactor_cls.name, compactor_cls.version
        compactor_endpoint_kind = compactor_base.endpoint_kind
    if reader_provider is not None:
        reader_base = reader_provider
    elif compactor_base is not None and args.resolved_reader_provider == args.provider_key:
        reader_base = compactor_base
    else:
        reader_base = _instantiate_provider(args.resolved_reader_provider)

    start = RunStartEvent(
        run_id=str(uuid.uuid4()),
        method_name=method_name,
        method_version=method_version,
        suite=suite.key,
        suite_version=suite.version,
        season=args.season,
        difficulty=cases[0].difficulty,
        drift_cycles=cases[0].drift_cycles,
        cases_per_family=args.cases_per_family or suite.cases_per_family,
        seed_group=args.seed_group,
        compactor_provider=args.provider_key,
        compactor_model=args.model,
        compactor_endpoint_kind=compactor_endpoint_kind,
        reader_provider=args.resolved_reader_provider,
        reader_model=args.resolved_reader_model,
        reader_endpoint_kind=reader_base.endpoint_kind,
        reader_effort=args.reader_effort,
        budget_tokens=args.budget_tokens,
        controls=args.controls,
        scorer_version=SCORER_VERSION,
        started_at=datetime.now(UTC),
    )

    already_done: set[str] = set()
    append = False
    if args.resume and args.output_path.exists():
        existing = read_run_start(args.output_path)
        if existing is None:
            raise ResumeError(f"--resume passed but {args.output_path} has no run_start event")
        _assert_resume_compatible(existing, start)
        start = existing
        already_done = completed_case_ids(args.output_path)
        append = True

    # The oracle control exists to show what losing nothing scores, so the
    # budget would defeat its purpose. It is never ranked.
    budget = None if method_name == OracleCompactor.name else args.budget_tokens
    writer = ResultsWriter(args.output_path, mode="append" if append else "write")
    traces = TraceWriter(args.traces_path, append=append) if args.traces_path else None
    try:
        if not append:
            writer.write(start)

        pending = [c for c in cases if c.case_id not in already_done]
        semaphore = asyncio.Semaphore(max(1, args.concurrency))

        async def _run_one(case: GeneratedCase) -> CaseResult:
            async with semaphore:
                # Fresh wrappers and compactor per case: token attribution stays
                # per case under concurrency, and per-instance method state never
                # leaks between cases. The underlying clients are shared.
                compactor: Compactor
                if args.sandbox is not None:
                    compactor_counter = usage_counter()
                    compactor = SandboxedCompactor(
                        args.sandbox,
                        method_spec=args.method_spec,
                        provider_key=args.provider_key,
                        model=args.model,
                        config=args.method_config,
                        usage=compactor_counter,
                    )
                else:
                    assert compactor_cls is not None
                    assert compactor_base is not None
                    compactor_counter = CountingProvider(compactor_base)
                    compactor = compactor_cls(compactor_counter, args.model, args.method_config)
                try:
                    return await _execute_case(
                        case=case,
                        run_id=start.run_id,
                        compactor=compactor,
                        compactor_provider=compactor_counter,
                        reader=CountingProvider(reader_base),
                        control_reader=CountingProvider(reader_base),
                        reader_model=args.resolved_reader_model,
                        budget_tokens=budget,
                        controls=args.controls,
                        chunk_size=args.chunk_size,
                        reader_effort=args.reader_effort,
                        traces=traces,
                    )
                finally:
                    await compactor.aclose()

        tasks = [asyncio.create_task(_run_one(c)) for c in pending]
        completed: list[CaseResult] = []
        try:
            for coro in asyncio.as_completed(tasks):
                case_result = await coro
                writer.write(CaseCompleteEvent(case_result=case_result))
                completed.append(case_result)
        except Exception:
            for t in tasks:
                t.cancel()
            raise

        all_cases = list(completed)
        if already_done:
            all_cases.extend(
                event.case_result
                for event in iter_events(args.output_path)
                if isinstance(event, CaseCompleteEvent)
                and event.case_result.case_id in already_done
            )
        writer.write(
            RunEndEvent(
                completed_at=datetime.now(UTC),
                metrics=compute_metrics(all_cases),
                token_usage=sum_case_token_usage(all_cases),
            )
        )
    finally:
        writer.close()
        if traces is not None:
            traces.close()

    return args.output_path


async def _execute_case(
    *,
    case: GeneratedCase,
    run_id: str,
    compactor: Compactor,
    compactor_provider: CountingProvider,
    reader: CountingProvider,
    control_reader: CountingProvider,
    reader_model: str,
    budget_tokens: int | None,
    controls: bool,
    chunk_size: int,
    reader_effort: ReasoningEffort | None,
    traces: TraceWriter | None,
) -> CaseResult:
    previous: CompactionArtifact | None = None
    cycles: list[CycleResult] = []
    usage = None
    for index in range(len(case.cycles)):
        execution = await execute_cycle(
            case=case,
            cycle=index,
            previous_artifact=previous,
            compactor=compactor,
            compactor_provider=compactor_provider,
            reader=reader,
            reader_model=reader_model,
            budget_tokens=budget_tokens,
            controls=controls,
            control_reader=control_reader,
            chunk_size=chunk_size,
            reader_effort=reader_effort,
        )
        result = execution.result
        cycles.append(result)
        previous = execution.artifact
        for part in (result.compactor_usage, result.reader_usage, result.control_usage):
            usage = add_usage(usage, part)
        if traces is not None:
            traces.write_cycle(
                run_id=run_id,
                case_id=case.case_id,
                result=result,
                turn_ids=execution.turn_ids,
                artifact=execution.artifact,
                visible_context=execution.visible_context,
                probes=case.cycles[index].probes,
                answers=execution.answers,
                reader_responses=execution.reader_responses,
            )

    scores = counted(r for cycle in cycles for r in cycle.probe_results)
    return CaseResult(
        case_id=case.case_id,
        family=case.family,
        seed=case.seed,
        cycles=cycles,
        score=fmean(scores) if scores else 0.0,
        token_usage=usage,
    )


def _instantiate_provider(provider_key: str) -> Provider:
    cls = get_provider_cls(provider_key)
    # All real providers accept keyword-only args; mock accepts no args.
    return cls()


_RESUME_FIELDS = (
    "method_name",
    "method_version",
    "suite",
    "suite_version",
    "season",
    "difficulty",
    "drift_cycles",
    "cases_per_family",
    "seed_group",
    "compactor_provider",
    "compactor_model",
    "compactor_endpoint_kind",
    "reader_provider",
    "reader_model",
    "reader_endpoint_kind",
    "reader_effort",
    "budget_tokens",
    "controls",
    "scorer_version",
)


def _assert_resume_compatible(existing: RunStartEvent, requested: RunStartEvent) -> None:
    """Refuse to resume a run under different parameters — including where calls go."""
    mismatches = [
        f"{name}: {getattr(existing, name)!r} vs {getattr(requested, name)!r}"
        for name in _RESUME_FIELDS
        if getattr(existing, name) != getattr(requested, name)
    ]
    if mismatches:
        raise ResumeError(
            "existing run is incompatible with requested arguments: " + "; ".join(mismatches)
        )
