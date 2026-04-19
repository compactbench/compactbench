"""Top-level run orchestrator.

Loads a suite, generates one case per (template, seed slot), executes each
case through all drift cycles, scores everything, and writes a streamed
``results.jsonl`` event log.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from compactbench.compactors import Compactor
from compactbench.contracts import CaseResult, CycleResult, GeneratedCase
from compactbench.dsl import (
    DifficultyLevel,
    TemplateDefinition,
    load_suite,
    validate_template,
)
from compactbench.engine import derive_case_seed, generate_case
from compactbench.providers import Provider, get_provider_cls
from compactbench.runner._resolver import resolve_compactor_class
from compactbench.runner.cycle import execute_cycle
from compactbench.runner.errors import ResumeError, RunnerError
from compactbench.runner.persistence import (
    SCORER_VERSION,
    CaseCompleteEvent,
    ResultsWriter,
    RunEndEvent,
    RunStartEvent,
    aggregate_run_metrics,
    completed_case_ids,
    read_run_start,
)
from compactbench.scoring import drift_resistance


@dataclass(frozen=True)
class RunArgs:
    method_spec: str
    suite_key: str
    provider_key: str
    model: str
    difficulty: DifficultyLevel
    drift_cycles: int
    case_count_per_template: int
    seed_group: str
    benchmarks_dir: Path
    output_path: Path
    resume: bool
    # Maximum number of cases evaluated concurrently. Set to 1 to reproduce the
    # original serial behaviour; higher values parallelise the I/O-bound
    # provider calls, yielding a roughly linear wall-clock speedup until the
    # provider's rate limit or the local event loop becomes the bottleneck.
    concurrency: int = 4


async def run_experiment(args: RunArgs) -> Path:
    """Execute a full run per ``args`` and return the path to the written results file."""
    suite_dir = args.benchmarks_dir / args.suite_key
    if not suite_dir.is_dir():
        raise RunnerError(f"suite directory not found: {suite_dir}")

    templates = load_suite(suite_dir)
    if not templates:
        raise RunnerError(f"no templates in suite {args.suite_key!r}")
    for template in templates:
        validate_template(template)

    compactor_cls = resolve_compactor_class(args.method_spec)
    provider = _instantiate_provider(args.provider_key)

    already_done: set[str] = set()
    run_id: str
    started_at: datetime
    mode: str = "write"

    if args.resume and args.output_path.exists():
        existing = read_run_start(args.output_path)
        if existing is None:
            raise ResumeError(f"--resume passed but {args.output_path} has no run_start event")
        _assert_resume_compatible(existing, args, compactor_cls)
        already_done = completed_case_ids(args.output_path)
        run_id = existing.run_id
        started_at = existing.started_at
        mode = "append"
    else:
        run_id = str(uuid.uuid4())
        started_at = datetime.now(UTC)

    suite_version = _suite_version(templates)
    writer = ResultsWriter(args.output_path, mode=mode)  # type: ignore[arg-type]
    try:
        if mode == "write":
            writer.write(
                RunStartEvent(
                    run_id=run_id,
                    method_name=compactor_cls.name,
                    method_version=compactor_cls.version,
                    suite_key=args.suite_key,
                    suite_version=suite_version,
                    scorer_version=SCORER_VERSION,
                    target_provider=args.provider_key,
                    target_model=args.model,
                    difficulty=args.difficulty.value,
                    drift_cycles=args.drift_cycles,
                    seed_group=args.seed_group,
                    case_count_per_template=args.case_count_per_template,
                    started_at=started_at,
                )
            )

        # Build the list of (case, seed) pairs the run still needs to execute.
        # Case generation is deterministic and side-effect-free, so we can
        # expand everything up-front and then schedule the I/O-bound work
        # concurrently under a semaphore.
        pending: list[tuple[GeneratedCase, int]] = []
        for template in templates:
            # Namespace the seed with (suite, template) so slot N of two different
            # templates doesn't deterministically share variable choices — that
            # would correlate "Alice" / "Bob" style bindings across families and
            # weaken adversarial diversity.
            seed_namespace = f"{args.suite_key}@{suite_version}/{template.key}@{template.version}"
            for slot in range(args.case_count_per_template):
                case_seed = derive_case_seed(seed_namespace, args.seed_group, slot)
                case = generate_case(template, case_seed, args.difficulty)
                if case.case_id in already_done:
                    continue
                pending.append((case, case_seed))

        concurrency = max(1, args.concurrency)
        semaphore = asyncio.Semaphore(concurrency)

        async def _run_one(case: GeneratedCase, case_seed: int) -> CaseResult:
            """Execute a single case under the global concurrency semaphore.

            A fresh compactor instance per case keeps any per-instance state
            (e.g. ledger accumulators) scoped to the case, matching the
            previous serial behaviour exactly.
            """
            async with semaphore:
                compactor = compactor_cls(provider, args.model)
                return await _execute_case(
                    case=case,
                    compactor=compactor,
                    provider=provider,
                    model=args.model,
                    drift_cycles=args.drift_cycles,
                    case_seed=case_seed,
                )

        tasks = [asyncio.create_task(_run_one(c, s)) for c, s in pending]
        completed_cases: list[CaseResult] = []
        try:
            for coro in asyncio.as_completed(tasks):
                case_result = await coro
                # Writer is called from a single awaiting coroutine so
                # individual writes remain atomic even though cases complete
                # out of their original enumeration order.
                writer.write(CaseCompleteEvent(case_result=case_result))
                completed_cases.append(case_result)
        except Exception:
            for t in tasks:
                t.cancel()
            raise

        # For run-end aggregates, combine newly-executed cases with any that
        # were already persisted from a resumed run.
        from compactbench.runner.persistence import iter_events

        all_cases: list[CaseResult] = list(completed_cases)
        if already_done:
            for event in iter_events(args.output_path):
                if (
                    isinstance(event, CaseCompleteEvent)
                    and event.case_result.case_id in already_done
                ):
                    all_cases.append(event.case_result)

        agg = aggregate_run_metrics(all_cases)
        writer.write(
            RunEndEvent(
                completed_at=datetime.now(UTC),
                overall_score=agg["overall_score"],
                drift_resistance=agg["drift_resistance"],
                constraint_retention=agg["constraint_retention"],
                contradiction_rate=agg["contradiction_rate"],
                compression_ratio=agg["compression_ratio"],
            )
        )
    finally:
        writer.close()

    return args.output_path


async def _execute_case(
    *,
    case: GeneratedCase,
    compactor: Compactor,
    provider: Provider,
    model: str,
    drift_cycles: int,
    case_seed: int,
) -> CaseResult:
    from compactbench.contracts import CompactionArtifact, Transcript

    transcript: Transcript = case.transcript
    previous_artifact: CompactionArtifact | None = None
    cycles: list[CycleResult] = []
    cycle_scores: list[float] = []

    for cycle_num in range(drift_cycles + 1):
        result = await execute_cycle(
            case=case,
            transcript=transcript,
            cycle_number=cycle_num,
            previous_artifact=previous_artifact,
            compactor=compactor,
            provider=provider,
            model=model,
            case_seed=case_seed,
        )
        drift_delta = (
            result.scorecard.penalized_cycle_score - cycle_scores[0]
            if cycle_num > 0 and cycle_scores
            else None
        )
        cycles.append(
            CycleResult(
                cycle_number=cycle_num,
                scorecard=result.scorecard,
                drift_delta=drift_delta,
                latency_ms=result.latency_ms,
            )
        )
        cycle_scores.append(result.scorecard.penalized_cycle_score)
        transcript = result.extended_transcript
        previous_artifact = result.artifact

    case_score = sum(cycle_scores) / len(cycle_scores) if cycle_scores else 0.0
    return CaseResult(
        case_id=case.case_id,
        template_key=case.template_key,
        seed=case.seed,
        cycles=cycles,
        case_score=case_score,
        drift_resistance=drift_resistance(cycle_scores),
    )


def _instantiate_provider(provider_key: str) -> Provider:
    cls = get_provider_cls(provider_key)
    # All real providers accept keyword-only args; mock accepts no args.
    return cls()


def _suite_version(templates: list[TemplateDefinition]) -> str:
    versions = {t.version for t in templates}
    if len(versions) == 1:
        return next(iter(versions))
    return "mixed"


def _assert_resume_compatible(
    existing: RunStartEvent, args: RunArgs, compactor_cls: type[Compactor]
) -> None:
    mismatches: list[str] = []
    if existing.method_name != compactor_cls.name:
        mismatches.append(f"method_name: {existing.method_name!r} vs {compactor_cls.name!r}")
    if existing.suite_key != args.suite_key:
        mismatches.append(f"suite_key: {existing.suite_key!r} vs {args.suite_key!r}")
    if existing.target_provider != args.provider_key:
        mismatches.append(f"provider: {existing.target_provider!r} vs {args.provider_key!r}")
    if existing.target_model != args.model:
        mismatches.append(f"model: {existing.target_model!r} vs {args.model!r}")
    if existing.difficulty != args.difficulty.value:
        mismatches.append(f"difficulty: {existing.difficulty!r} vs {args.difficulty.value!r}")
    if existing.drift_cycles != args.drift_cycles:
        mismatches.append(f"drift_cycles: {existing.drift_cycles} vs {args.drift_cycles}")
    if existing.seed_group != args.seed_group:
        mismatches.append(f"seed_group: {existing.seed_group!r} vs {args.seed_group!r}")
    if existing.case_count_per_template != args.case_count_per_template:
        mismatches.append(
            f"case_count_per_template: "
            f"{existing.case_count_per_template} vs {args.case_count_per_template}"
        )
    if mismatches:
        raise ResumeError(
            "existing run is incompatible with requested arguments: " + "; ".join(mismatches)
        )
