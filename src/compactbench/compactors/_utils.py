"""Helpers used across compactor implementations."""

from __future__ import annotations

from typing import TypeVar

from compactbench.contracts import Transcript, Turn

T = TypeVar("T")


def render_transcript(transcript: Transcript) -> str:
    """Render a transcript as a plain text prompt body."""
    return render_turns(list(transcript.turns))


def render_turns(turns: list[Turn]) -> str:
    """Render an arbitrary list of turns as a plain text prompt body."""
    return "\n\n".join(f"{turn.role.value.upper()}: {turn.content}" for turn in turns)


def chunk(items: list[T], size: int) -> list[list[T]]:
    """Split ``items`` into groups of ``size`` (last group may be smaller)."""
    if size <= 0:
        raise ValueError(f"chunk size must be > 0, got {size}")
    return [items[i : i + size] for i in range(0, len(items), size)]


def uniq_preserve_order(items: list[str]) -> list[str]:
    """Return ``items`` with duplicates removed, preserving first-occurrence order."""
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


#: Maximum characters ``CompactionArtifact.summary_text`` accepts. Mirrored here
#: so compactors can fit their output *before* constructing the artifact rather
#: than discovering the limit as a pydantic ValidationError.
SUMMARY_TEXT_LIMIT = 8000


def fit_summary_text(text: str, *, limit: int = SUMMARY_TEXT_LIMIT) -> tuple[str, list[str]]:
    """Trim ``text`` to the artifact's summary cap, reporting whether it cut.

    ``CompactionArtifact.summary_text`` is capped at 8000 characters, and three
    built-in compactors passed raw model output straight into it. A model that
    ignores "be concise" — which small and local models routinely do — therefore
    raised a ``ValidationError`` that propagated out of the compactor and
    aborted the **entire run**. Observed for real: one over-long `naive-summary`
    response destroyed a 20-case baseline four cases in.

    Truncating is the right behaviour rather than raising. A method whose model
    overruns the artifact budget has a method-quality problem, and a serious
    compactor handles that itself; the benchmark should measure the result — a
    truncated artifact scores worse, which is the correct signal — instead of
    losing every other case in the run to one verbose response.

    The truncation is recorded in the artifact's ``warnings`` so it is visible in
    ``results.jsonl`` rather than silent.
    """
    if len(text) <= limit:
        return text, []
    return text[:limit], [
        f"summary_text exceeded the {limit}-character artifact limit "
        f"({len(text)} chars) and was truncated; the method should compress further"
    ]
