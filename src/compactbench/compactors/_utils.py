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
