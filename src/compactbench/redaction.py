"""Public copies of results files, with nothing from a hidden case left in them.

Two fields in a results file come from the case or the method rather than the harness:

- **Probe keys** name the people, rules, topics and tickets of the world a question was
  about (``entity_confusion/role_<name>``). For a private world that is private
  vocabulary, and fresh sampling would leak more of it with every published run.
- **Cycle warnings** are the method's own free text — a channel a submitted method
  controls.

A redacted copy replaces every key with ``<family>/<digest>``, an HMAC over the case
id and the key under a random per-file salt — equal within a case, so drift metrics
are unchanged, and unlinkable across cases and runs — and drops the warnings. Scores,
flags, token counts and settings are untouched, so the leaderboard reads a redacted
file exactly as it reads the original.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from pathlib import Path

from compactbench.contracts import CaseResult, CycleResult
from compactbench.runner.persistence import CaseCompleteEvent, ResultsWriter, iter_events

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


def redact_results(source: Path, target: Path, *, salt: bytes | None = None) -> None:
    """Write a redacted copy of the results file ``source`` to ``target``."""
    salt = salt if salt is not None else secrets.token_bytes(32)
    events = list(iter_events(source))
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
