"""Run orchestration: suite → cases → compaction cycles → scored results.

The public surface is :func:`run_experiment` plus persistence helpers; the CLI
wires these together.
"""

from compactbench.runner._resolver import resolve_compactor_class
from compactbench.runner.cycle import CycleExecution, execute_cycle
from compactbench.runner.errors import MethodResolutionError, ResumeError, RunnerError
from compactbench.runner.persistence import (
    INCOMPLETE_RUN_NOTE,
    RESULTS_SCHEMA,
    SCORER_VERSION,
    CaseCompleteEvent,
    ResultsWriter,
    RunEndEvent,
    RunStartEvent,
    completed_case_ids,
    iter_events,
    read_run_start,
    sum_case_token_usage,
    to_run_result,
)
from compactbench.runner.reader import READER_SYSTEM, ReaderOutcome, read
from compactbench.runner.run import DEFAULT_BUDGET_TOKENS, RunArgs, run_experiment
from compactbench.runner.traces import TraceWriter

__all__ = [
    "DEFAULT_BUDGET_TOKENS",
    "INCOMPLETE_RUN_NOTE",
    "READER_SYSTEM",
    "RESULTS_SCHEMA",
    "SCORER_VERSION",
    "CaseCompleteEvent",
    "CycleExecution",
    "MethodResolutionError",
    "ReaderOutcome",
    "ResultsWriter",
    "ResumeError",
    "RunArgs",
    "RunEndEvent",
    "RunStartEvent",
    "RunnerError",
    "TraceWriter",
    "completed_case_ids",
    "execute_cycle",
    "iter_events",
    "read",
    "read_run_start",
    "resolve_compactor_class",
    "run_experiment",
    "sum_case_token_usage",
    "to_run_result",
]
