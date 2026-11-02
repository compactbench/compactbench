"""Helpers for compactor implementations."""

from __future__ import annotations

import pytest

from compactbench.compactors._utils import (
    SUMMARY_TEXT_LIMIT,
    budget_instruction,
    chunk,
    finalize,
    fit_summary_text,
    output_tokens,
    reasoning_effort,
    uniq_preserve_order,
)
from compactbench.contracts import CompactionArtifact, CompactionRequest

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


def test_budget_instruction_scales_with_budget() -> None:
    small = budget_instruction(CompactionRequest(cycle=0, turns=[], token_budget=1000))
    large = budget_instruction(CompactionRequest(cycle=0, turns=[], token_budget=4000))
    assert "700 words" in small
    assert "2800 words" in large


def test_budget_instruction_without_budget() -> None:
    assert budget_instruction(CompactionRequest(cycle=0, turns=[])) == "Be concise."


def test_budget_instruction_share() -> None:
    req = CompactionRequest(cycle=0, turns=[], token_budget=2000)
    assert "700 words" in budget_instruction(req, share=0.5)


class TestFitSummaryText:
    """Regression: an over-long model response used to abort the whole run.

    `CompactionArtifact.summary_text` has a hard character cap and built-in
    compactors pass raw model output straight into it. A model that
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
        _, warnings = fit_summary_text("x" * (SUMMARY_TEXT_LIMIT + 2345))
        assert str(SUMMARY_TEXT_LIMIT + 2345) in warnings[0]

    def test_the_fitted_result_always_validates_against_the_contract(self) -> None:
        """The whole point: whatever comes back must construct an artifact."""
        fitted, _ = fit_summary_text("x" * (SUMMARY_TEXT_LIMIT + 50_000))
        artifact = CompactionArtifact(summaryText=fitted)
        assert len(artifact.summary_text) == SUMMARY_TEXT_LIMIT


class TestFitToBudget:
    def _big(self) -> CompactionArtifact:
        from compactbench.contracts import StructuredState

        return CompactionArtifact(
            summaryText="short header",
            structured_state=StructuredState(
                locked_decisions=[f"decision {i}: " + "word " * 20 for i in range(30)],
                forbidden_behaviors=["never do the thing"],
            ),
        )

    def test_under_budget_is_untouched(self) -> None:
        artifact = CompactionArtifact(summaryText="tiny")
        req = CompactionRequest(cycle=0, turns=[], token_budget=100)
        assert finalize(artifact, req) == artifact

    def test_drops_oldest_entries_of_largest_section_first(self) -> None:
        from compactbench.rendering import render_artifact
        from compactbench.tokens import count_tokens

        req = CompactionRequest(cycle=0, turns=[], token_budget=200)
        fitted = finalize(self._big(), req)
        assert count_tokens(render_artifact(fitted)) <= 200
        decisions = fitted.structured_state.locked_decisions
        assert decisions
        assert decisions[-1].startswith("decision 29")
        assert fitted.structured_state.forbidden_behaviors == ["never do the thing"]
        assert any("trimmed to fit" in w for w in fitted.warnings)

    def test_output_tokens_leave_room_for_thinking(self) -> None:
        assert output_tokens(CompactionRequest(cycle=0, turns=[])) == 16_000
        assert output_tokens(CompactionRequest(cycle=0, turns=[], token_budget=4096)) == 16_000


class TestReasoningEffort:
    def test_defaults_to_low(self) -> None:
        assert reasoning_effort({}) == "low"

    def test_null_leaves_it_to_the_model(self) -> None:
        assert reasoning_effort({"effort": None}) is None

    def test_rejects_unknown_values(self) -> None:
        with pytest.raises(ValueError, match="effort"):
            reasoning_effort({"effort": "max"})
