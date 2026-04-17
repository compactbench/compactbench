"""Helpers for compactor implementations."""

from __future__ import annotations

import pytest

from compactbench.compactors._utils import (
    chunk,
    render_transcript,
    render_turns,
    uniq_preserve_order,
)
from compactbench.contracts import Transcript, Turn, TurnRole

pytestmark = pytest.mark.unit


def test_chunk_exact_division() -> None:
    assert chunk([1, 2, 3, 4], 2) == [[1, 2], [3, 4]]


def test_chunk_remainder() -> None:
    assert chunk([1, 2, 3, 4, 5], 2) == [[1, 2], [3, 4], [5]]


def test_chunk_size_larger_than_list() -> None:
    assert chunk([1, 2], 10) == [[1, 2]]


def test_chunk_empty_list() -> None:
    assert chunk([], 3) == []


def test_chunk_negative_size_raises() -> None:
    with pytest.raises(ValueError, match="> 0"):
        chunk([1, 2, 3], 0)


def test_uniq_preserves_order() -> None:
    assert uniq_preserve_order(["b", "a", "a", "c", "b"]) == ["b", "a", "c"]


def test_uniq_preserves_empty() -> None:
    assert uniq_preserve_order([]) == []


def test_render_transcript_includes_role_and_content() -> None:
    t = Transcript(
        turns=[
            Turn(id=0, role=TurnRole.USER, content="hello"),
            Turn(id=1, role=TurnRole.ASSISTANT, content="hi"),
        ]
    )
    rendered = render_transcript(t)
    assert "USER: hello" in rendered
    assert "ASSISTANT: hi" in rendered


def test_render_turns_handles_empty() -> None:
    assert render_turns([]) == ""
