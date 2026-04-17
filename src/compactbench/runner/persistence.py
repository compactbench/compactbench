"""JSONL event log for run results.

Each run writes a sequence of events to a single ``results.jsonl`` file:

- one ``run_start`` event at the top with run metadata
- one ``case_complete`` event per completed case (streamed as they finish)
- one ``run_end`` event at the bottom with run-level aggregates

Writer flushes after every event so partial results survive crashes and
``--resume`` can pick up where we left off. Reader aggregates the stream into
a :class:`RunResult`.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from types import TracebackType
from typing import IO, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from compactbench.contracts import CaseResult, RunResult

SCORER_VERSION: str = "1.0.0"


class RunStartEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    event: Literal["run_start"] = "run_start"
    run_id: str
    method_name: str
    method_version: str
    suite_key: str
    suite_version: str
    scorer_version: str
    target_provider: str
    target_model: str
    difficulty: str
    drift_cycles: int
    seed_group: str
    case_count_per_template: int
    started_at: datetime


class CaseCompleteEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    event: Literal["case_complete"] = "case_complete"
    case_result: CaseResult


class RunEndEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    event: Literal["run_end"] = "run_end"
    completed_at: datetime
    overall_score: float = Field(ge=0.0, le=1.0)
    drift_resistance: float = Field(ge=0.0, le=1.0)
    constraint_retention: float = Field(ge=0.0, le=1.0)
    contradiction_rate: float = Field(ge=0.0, le=1.0)
    compression_ratio: float = Field(ge=0.0)
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
    """Yield every event parsed from ``path``."""
    with path.open(encoding="utf-8") as fp:
        for line_num, line in enumerate(fp, start=1):
            text = line.strip()
            if not text:
                continue
            try:
                yield _EVENT_ADAPTER.validate_json(text)
            except Exception as exc:
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


def to_run_result(path: Path) -> RunResult:
    """Aggregate every event in ``path`` into a :class:`RunResult`.

    Raises :class:`ValueError` if there is no ``run_start`` event.
    """
    run_start: RunStartEvent | None = None
    cases: list[CaseResult] = []
    run_end: RunEndEvent | None = None

    for event in iter_events(path):
        if isinstance(event, RunStartEvent):
            run_start = event
        elif isinstance(event, CaseCompleteEvent):
            cases.append(event.case_result)
        else:
            run_end = event

    if run_start is None:
        raise ValueError(f"{path}: no run_start event found")

    if run_end is not None:
        end: RunEndEvent = run_end
        completed_at = end.completed_at
        overall_score = end.overall_score
        drift_resistance = end.drift_resistance
        constraint_retention = end.constraint_retention
        contradiction_rate = end.contradiction_rate
        compression_ratio = end.compression_ratio
        notes = list(end.notes)
    else:
        # Run was interrupted — derive aggregates from whatever cases landed.
        agg = aggregate_run_metrics(cases)
        completed_at = run_start.started_at
        overall_score = agg["overall_score"]
        drift_resistance = agg["drift_resistance"]
        constraint_retention = agg["constraint_retention"]
        contradiction_rate = agg["contradiction_rate"]
        compression_ratio = agg["compression_ratio"]
        notes = ["run_end event missing: results may be incomplete"]

    return RunResult(
        run_id=run_start.run_id,
        method_name=run_start.method_name,
        method_version=run_start.method_version,
        suite_key=run_start.suite_key,
        suite_version=run_start.suite_version,
        scorer_version=run_start.scorer_version,
        target_provider=run_start.target_provider,
        target_model=run_start.target_model,
        started_at=run_start.started_at,
        completed_at=completed_at,
        cases=cases,
        overall_score=overall_score,
        drift_resistance=drift_resistance,
        constraint_retention=constraint_retention,
        contradiction_rate=contradiction_rate,
        compression_ratio=compression_ratio,
        notes=notes,
    )


def aggregate_run_metrics(case_results: list[CaseResult]) -> dict[str, float]:
    """Compute run-level aggregate metrics from a list of case results."""
    if not case_results:
        return {
            "overall_score": 0.0,
            "drift_resistance": 1.0,
            "constraint_retention": 0.0,
            "contradiction_rate": 0.0,
            "compression_ratio": 0.0,
        }

    def _mean(values: list[float], default: float = 0.0) -> float:
        return sum(values) / len(values) if values else default

    all_cycles = [cycle for cr in case_results for cycle in cr.cycles]

    constraint_scores: list[float] = []
    for cr in case_results:
        for cycle in cr.cycles:
            for item_score in cycle.scorecard.item_scores:
                if item_score.item_type in (
                    "locked_decision_retention",
                    "forbidden_behavior_retention",
                ):
                    constraint_scores.append(item_score.score)

    return {
        "overall_score": _mean([cr.case_score for cr in case_results]),
        "drift_resistance": _mean([cr.drift_resistance for cr in case_results], default=1.0),
        "constraint_retention": _mean(constraint_scores),
        "contradiction_rate": _mean([cycle.scorecard.contradiction_rate for cycle in all_cycles]),
        "compression_ratio": _mean([cycle.scorecard.compression_ratio for cycle in all_cycles]),
    }
