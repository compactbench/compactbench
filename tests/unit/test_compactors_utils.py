"""Helpers for compactor implementations."""

from __future__ import annotations

import pytest

from compactbench.compactors._utils import (
    SUMMARY_TEXT_LIMIT,
    chunk,
    fit_summary_text,
    render_transcript,
    render_turns,
    uniq_preserve_order,
)
from compactbench.contracts import CompactionArtifact, Transcript, Turn, TurnRole

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


class TestFitSummaryText:
    """Regression: an over-long model response used to abort the whole run.

    `CompactionArtifact.summary_text` is capped at 8000 characters and three
    built-in compactors passed raw model output straight into it. A model that
    ignores "be concise" — routine for small and local models — raised a
    ValidationError out of the compactor and killed every remaining case. This
    was observed for real: one verbose `naive-summary` response destroyed a
    20-case baseline run four cases in.
    """

    def test_short_text_passes_through_unchanged_with_no_warning(self) -> None:
        text = "a concise summary"
        assert fit_summary_text(text) == (text, [])

    def test_text_at_exactly_the_limit_is_not_truncated(self) -> None:
        text = "x" * SUMMARY_TEXT_LIMIT
        fitted, warnings = fit_summary_text(text)
        assert fitted == text
        assert warnings == []

    def test_over_long_text_is_truncated_and_warned(self) -> None:
        fitted, warnings = fit_summary_text("x" * (SUMMARY_TEXT_LIMIT + 1000))
        assert len(fitted) == SUMMARY_TEXT_LIMIT
        assert len(warnings) == 1
        assert "truncated" in warnings[0]

    def test_warning_reports_the_original_length(self) -> None:
        """A submitter needs to know how far over they were, not just that they were."""
        _, warnings = fit_summary_text("x" * 12345)
        assert "12345" in warnings[0]

    def test_the_fitted_result_always_validates_against_the_contract(self) -> None:
        """The whole point: whatever comes back must construct an artifact."""
        fitted, _ = fit_summary_text("x" * 50_000)
        artifact = CompactionArtifact(summaryText=fitted)
        assert len(artifact.summary_text) == SUMMARY_TEXT_LIMIT
