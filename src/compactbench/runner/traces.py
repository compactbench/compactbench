"""Full per-cycle traces: everything needed to see *why* a probe was missed.

Traces contain the conversation, the artifacts, the questions and the reader's
raw replies, so for ranked suites they reveal hidden content and must stay
private. Results files never contain any of this.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from types import TracebackType
from typing import IO, Any

from compactbench.contracts import CompactionArtifact, CycleResult, Probe


class TraceWriter:
    """Append-only JSONL writer, one record per (case, cycle). Safe across tasks."""

    def __init__(self, path: Path, *, append: bool = False) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._fp: IO[str] = path.open("a" if append else "w", encoding="utf-8")
        self._lock = threading.Lock()

    def write_cycle(
        self,
        *,
        run_id: str,
        case_id: str,
        result: CycleResult,
        turn_ids: list[int],
        artifact: CompactionArtifact,
        visible_context: str,
        probes: list[Probe],
        answers: dict[str, object],
        reader_responses: list[str],
    ) -> None:
        record: dict[str, Any] = {
            "run_id": run_id,
            "case_id": case_id,
            "cycle": result.cycle,
            "turn_ids": turn_ids,
            "artifact": artifact.model_dump(mode="json", by_alias=True),
            "visible_context": visible_context,
            "probes": [p.model_dump(mode="json") for p in probes],
            "answers": answers,
            "reader_responses": reader_responses,
            "result": result.model_dump(mode="json"),
        }
        line = json.dumps(record, ensure_ascii=False, default=str)
        with self._lock:
            self._fp.write(line + "\n")
            self._fp.flush()

    def close(self) -> None:
        if not self._fp.closed:
            self._fp.close()

    def __enter__(self) -> TraceWriter:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()
