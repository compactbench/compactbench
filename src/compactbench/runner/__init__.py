"""Run orchestration: suite → cases → drift cycles → scored results.

Implements WO-007. The public surface is :func:`run_experiment` plus
persistence helpers; the CLI wires these together.
"""

from compactbench.runner._resolver import resolve_compactor_class
from compactbench.runner.continuation import extend_with_continuation
from compactbench.runner.cycle import CycleExecutionResult, execute_cycle
from compactbench.runner.errors import MethodResolutionError, ResumeError, RunnerError
from compactbench.runner.evaluation import (
    build_evaluation_prompt,
    evaluate_items,
    render_artifact_for_prompt,
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
from compactbench.runner.run import RunArgs, run_experiment

__all__ = [
    "SCORER_VERSION",
    "CaseCompleteEvent",
    "CycleExecutionResult",
    "MethodResolutionError",
    "ResultsWriter",
    "ResumeError",
    "RunArgs",
    "RunEndEvent",
    "RunStartEvent",
    "RunnerError",
    "aggregate_run_metrics",
    "build_evaluation_prompt",
    "completed_case_ids",
    "evaluate_items",
    "execute_cycle",
    "extend_with_continuation",
    "iter_events",
    "read_run_start",
    "render_artifact_for_prompt",
    "resolve_compactor_class",
    "run_experiment",
    "to_run_result",
]
