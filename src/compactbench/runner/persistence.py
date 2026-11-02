"""JSONL event log for run results.

Each run writes a sequence of events to a single ``results.jsonl`` file:

- one ``run_start`` event with everything needed to reproduce the run
- one ``case_complete`` event per completed case (streamed as they finish)
- one ``run_end`` event with run-level aggregates

The writer flushes after every event so partial results survive crashes and
``--resume`` can pick up where it left off. Results files hold scores only —
no conversation text, questions or artifacts — so they are safe to share;
those live in the optional traces file.

Aggregates are always recomputed from the case events when a file is read, so
a hand-edited ``run_end`` can't change what a run reports.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from types import TracebackType
from typing import IO, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from compactbench.contracts import CaseResult, RunMetrics, RunResult, TokenUsage, add_usage
from compactbench.scoring.metrics import compute_metrics

# 3.0.0 — benchmark v2: scenario families, true drift loop, structured probes
# scored mechanically, family-balanced score. Not comparable with 2.0.0 or
# 1.0.0; the leaderboard segments on scorer_version, so rows never mix.
SCORER_VERSION: str = "3.0.0"
RESULTS_SCHEMA: str = "2"

#: Stable marker attached to a RunResult reconstructed from a results file that
#: has no ``run_end`` event — the run crashed, was killed, or is still running.
#: Qualification refuses to rank it: its aggregates cover only the cases that
#: happened to finish, and stopping early must not be a way to cherry-pick.
INCOMPLETE_RUN_NOTE = "run_end event missing: results may be incomplete"


class RunStartEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    event: Literal["run_start"] = "run_start"
    results_schema: str = RESULTS_SCHEMA
    run_id: str
    method_name: str
    method_version: str
    suite: str
    suite_version: str
    season: str | None = None
    difficulty: str
    drift_cycles: int = Field(ge=0)
    cases_per_family: int = Field(ge=1)
    seed_group: str
    compactor_provider: str
    compactor_model: str
    compactor_endpoint_kind: str = "default"
    reader_provider: str
    reader_model: str
    reader_endpoint_kind: str = "default"
    reader_effort: str | None = None
    budget_tokens: int | None = None
    controls: bool = False
    scorer_version: str
    started_at: datetime


class CaseCompleteEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    event: Literal["case_complete"] = "case_complete"
    case_result: CaseResult


class RunEndEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    event: Literal["run_end"] = "run_end"
    completed_at: datetime
    metrics: RunMetrics
    token_usage: TokenUsage | None = None
    notes: list[str] = Field(default_factory=list[str])


ResultEvent = RunStartEvent | CaseCompleteEvent | RunEndEvent

_EVENT_ADAPTER: TypeAdapter[ResultEvent] = TypeAdapter(ResultEvent)


class ResultsWriter:
    """Append-only JSONL writer for run events."""

    def __init__(self, path: Path, mode: Literal["write", "append"] = "write") -> None:
        self._path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._fp: IO[str] = path.open("a" if mode == "append" else "w", encoding="utf-8")

    def write(self, event: ResultEvent) -> None:
        self._fp.write(event.model_dump_json() + "\n")
        self._fp.flush()

    def close(self) -> None:
        if not self._fp.closed:
            self._fp.close()

    def __enter__(self) -> ResultsWriter:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()


def iter_events(path: Path) -> Iterator[ResultEvent]:
    """Yield every event parsed from ``path``.

    A truncated final line (a crash between ``write`` and ``flush``) is dropped
    silently so ``--resume`` can recover; corruption anywhere earlier raises.
    """
    with path.open(encoding="utf-8") as fp:
        lines = fp.readlines()
    last_index = len(lines) - 1
    for line_num, line in enumerate(lines, start=1):
        text = line.strip()
        if not text:
            continue
        try:
            yield _EVENT_ADAPTER.validate_json(text)
        except Exception as exc:
            if line_num - 1 == last_index and not line.endswith("\n"):
                return
            raise ValueError(f"invalid event at {path}:{line_num}: {exc}") from exc


def read_run_start(path: Path) -> RunStartEvent | None:
    """Return the ``run_start`` event, or ``None`` if the file has none."""
    for event in iter_events(path):
        if isinstance(event, RunStartEvent):
            return event
        break
    return None


def completed_case_ids(path: Path) -> set[str]:
    """Return the set of case IDs whose ``case_complete`` event has been persisted."""
    if not path.exists():
        return set()
    return {
        event.case_result.case_id
        for event in iter_events(path)
        if isinstance(event, CaseCompleteEvent)
    }


def sum_case_token_usage(cases: list[CaseResult]) -> TokenUsage | None:
    total: TokenUsage | None = None
    for case in cases:
        total = add_usage(total, case.token_usage)
    return total


def to_run_result(path: Path) -> RunResult:
    """Aggregate every event in ``path`` into a :class:`RunResult`.

    Raises :class:`ValueError` if there is no ``run_start`` event or the file
    was written by a different results schema.
    """
    run_start: RunStartEvent | None = None
    cases: list[CaseResult] = []
    run_end: RunEndEvent | None = None

    try:
        for event in iter_events(path):
            if isinstance(event, RunStartEvent):
                run_start = event
            elif isinstance(event, CaseCompleteEvent):
                cases.append(event.case_result)
            else:
                run_end = event
    except ValueError as exc:
        raise ValueError(
            f"{exc}\n(results files from CompactBench 0.2 and earlier use a different "
            "format and can't be read by this version)"
        ) from exc

    if run_start is None:
        raise ValueError(f"{path}: no run_start event found")

    notes = list(run_end.notes) if run_end is not None else [INCOMPLETE_RUN_NOTE]
    completed_at = run_end.completed_at if run_end is not None else run_start.started_at
    return RunResult(
        run_id=run_start.run_id,
        method_name=run_start.method_name,
        method_version=run_start.method_version,
        suite=run_start.suite,
        suite_version=run_start.suite_version,
        season=run_start.season,
        difficulty=run_start.difficulty,
        drift_cycles=run_start.drift_cycles,
        compactor_provider=run_start.compactor_provider,
        compactor_model=run_start.compactor_model,
        compactor_endpoint_kind=run_start.compactor_endpoint_kind,
        reader_provider=run_start.reader_provider,
        reader_model=run_start.reader_model,
        reader_endpoint_kind=run_start.reader_endpoint_kind,
        reader_effort=run_start.reader_effort,
        seed_group=run_start.seed_group,
        cases_per_family=run_start.cases_per_family,
        budget_tokens=run_start.budget_tokens,
        controls=run_start.controls,
        scorer_version=run_start.scorer_version,
        started_at=run_start.started_at,
        completed_at=completed_at,
        cases=cases,
        metrics=compute_metrics(cases),
        token_usage=sum_case_token_usage(cases),
        notes=notes,
    )
