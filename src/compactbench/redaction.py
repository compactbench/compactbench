"""Public copies of results files, with nothing from a hidden case left in them.

Three fields in a results file come from the case or the method rather than the harness:

- **Probe keys** name the people, rules, topics and tickets of the world a question was
  about (``entity_confusion/role_<name>``). For a private world that is private
  vocabulary, and fresh sampling would leak more of it with every published run.
- **Cycle warnings** are the method's own free text — a channel a submitted method
  controls.
- **Compactor usage** is what a sandboxed method reports about its own model calls:
  numbers it chooses, so they could carry data, or misstate the method's cost.

A redacted copy replaces every key with ``<family>/<digest>``, an HMAC over the case
id and the key under a random per-file salt — equal within a case, so drift metrics
are unchanged, and unlinkable across cases and runs — and drops the warnings. Given the
usage the model proxy measured for the run, it also replaces each compaction's reported
usage with an even share of that total (and the case and run totals with the matching
sums), so the published cost is measured, not self-reported. Scores, flags, reader usage
and settings are untouched, so the leaderboard reads a redacted file exactly as it
reads the original.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from pathlib import Path

from compactbench.contracts import CaseResult, CycleResult, TokenUsage, add_usage
from compactbench.runner.persistence import (
    CaseCompleteEvent,
    ResultEvent,
    ResultsWriter,
    RunEndEvent,
    iter_events,
)

#: What a redacted key looks like.
REDACTED_KEY = re.compile(r"^[a-z_]+/[0-9a-f]{16}$")


def _digest(salt: bytes, case_id: str, key: str) -> str:
    return hmac.new(salt, f"{case_id}\x00{key}".encode(), hashlib.sha256).hexdigest()[:16]


def redact_case(case: CaseResult, salt: bytes) -> CaseResult:
    """``case`` with hashed probe keys and no method warnings."""
    cycles: list[CycleResult] = []
    for cycle in case.cycles:
        probes = [
            probe.model_copy(
                update={
                    "key": f"{probe.family or case.family}/{_digest(salt, case.case_id, probe.key)}"
                }
            )
            for probe in cycle.probe_results
        ]
        cycles.append(cycle.model_copy(update={"probe_results": probes, "warnings": []}))
    return case.model_copy(update={"cycles": cycles})


def _shares(total: int, n: int) -> list[int]:
    """``total`` split into ``n`` integers as evenly as possible, earlier ones larger."""
    base, extra = divmod(total, n)
    return [base + (1 if i < extra else 0) for i in range(n)]


def with_measured_usage(events: list[ResultEvent], measured: TokenUsage) -> list[ResultEvent]:
    """``events`` with every compaction's usage replaced by an even share of ``measured``.

    Case totals and the run total are recomputed from the cycles, so they stay consistent.
    """
    n = sum(len(e.case_result.cycles) for e in events if isinstance(e, CaseCompleteEvent))
    if n == 0:
        return events
    shares = [
        TokenUsage(prompt_tokens=p, completion_tokens=c, call_count=k)
        for p, c, k in zip(
            _shares(measured.prompt_tokens, n),
            _shares(measured.completion_tokens, n),
            _shares(measured.call_count, n),
            strict=True,
        )
    ]
    out: list[ResultEvent] = []
    run_total: TokenUsage | None = None
    i = 0
    for event in events:
        if isinstance(event, CaseCompleteEvent):
            cycles: list[CycleResult] = []
            case_total: TokenUsage | None = None
            for cycle in event.case_result.cycles:
                cycle = cycle.model_copy(update={"compactor_usage": shares[i]})
                i += 1
                for part in (cycle.compactor_usage, cycle.reader_usage, cycle.control_usage):
                    case_total = add_usage(case_total, part)
                cycles.append(cycle)
            case = event.case_result.model_copy(
                update={"cycles": cycles, "token_usage": case_total}
            )
            run_total = add_usage(run_total, case_total)
            event = event.model_copy(update={"case_result": case})
        elif isinstance(event, RunEndEvent):
            event = event.model_copy(update={"token_usage": run_total})
        out.append(event)
    return out


def redact_results(
    source: Path,
    target: Path,
    *,
    salt: bytes | None = None,
    compactor_usage: TokenUsage | None = None,
) -> None:
    """Write a redacted copy of the results file ``source`` to ``target``.

    ``compactor_usage``, when given, is the method's usage as the model proxy measured it;
    the copy then carries that instead of what the method reported.
    """
    salt = salt if salt is not None else secrets.token_bytes(32)
    events: list[ResultEvent] = list(iter_events(source))
    if compactor_usage is not None:
        events = with_measured_usage(events, compactor_usage)
    with ResultsWriter(target) as writer:
        for event in events:
            if isinstance(event, CaseCompleteEvent):
                event = event.model_copy(
                    update={"case_result": redact_case(event.case_result, salt)}
                )
            writer.write(event)


def is_redacted(path: Path) -> bool:
    """True when every probe key in ``path`` is hashed and no cycle has warnings."""
    for event in iter_events(path):
        if not isinstance(event, CaseCompleteEvent):
            continue
        for cycle in event.case_result.cycles:
            if cycle.warnings:
                return False
            if any(not REDACTED_KEY.match(p.key) for p in cycle.probe_results):
                return False
    return True
