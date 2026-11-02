"""Data contracts: probes, cases, requests, artifacts."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from compactbench.contracts import (
    NOT_STATED,
    CompactionArtifact,
    CompactionRequest,
    CycleSpec,
    GeneratedCase,
    Probe,
    ProbeCategory,
    ProbeFormat,
    TokenUsage,
    Turn,
    TurnRole,
    ValueKind,
    add_usage,
)

pytestmark = pytest.mark.unit


def _single(**overrides: object) -> Probe:
    fields: dict[str, object] = {
        "key": "k",
        "category": ProbeCategory.DECISION_STATE,
        "format": ProbeFormat.SINGLE,
        "question": "Which?",
        "options": ["A", "B", NOT_STATED],
        "answer": ["A"],
        "origin_cycle": 0,
    }
    fields.update(overrides)
    return Probe.model_validate(fields)


def _case(turn_ids: list[list[int]]) -> GeneratedCase:
    return GeneratedCase(
        case_id="c",
        family="f",
        family_version="1",
        suite="s",
        seed=1,
        difficulty="easy",
        setting="software",
        cycles=[
            CycleSpec(
                cycle=i,
                turns=[Turn(id=t, role=TurnRole.USER, content=f"t{t}") for t in ids],
                probes=[],
            )
            for i, ids in enumerate(turn_ids)
        ],
    )


class TestProbe:
    def test_valid_single(self) -> None:
        assert _single().answer == ["A"]

    def test_choice_needs_two_options(self) -> None:
        with pytest.raises(ValidationError, match="at least 2 options"):
            _single(options=["A"])

    def test_answer_must_be_an_option(self) -> None:
        with pytest.raises(ValidationError, match="not options"):
            _single(answer=["Z"])

    def test_single_needs_exactly_one_answer(self) -> None:
        with pytest.raises(ValidationError, match="one answer"):
            _single(answer=["A", "B"])

    def test_duplicate_options_rejected(self) -> None:
        with pytest.raises(ValidationError, match="duplicate"):
            _single(options=["A", "A"])

    def test_value_probe_takes_no_options(self) -> None:
        with pytest.raises(ValidationError, match="no options"):
            _single(format=ProbeFormat.VALUE, value_kind=ValueKind.MONEY)

    def test_multi_may_have_no_correct_answer(self) -> None:
        probe = _single(format=ProbeFormat.MULTI, answer=[])
        assert probe.answer == []


class TestGeneratedCase:
    def test_transcript_through_accumulates_cycles(self) -> None:
        case = _case([[0, 1], [2], [3, 4]])
        assert [t.id for t in case.transcript_through(1).turns] == [0, 1, 2]
        assert case.drift_cycles == 2

    def test_turn_ids_must_increase(self) -> None:
        with pytest.raises(ValidationError, match="increasing"):
            _case([[0, 2], [1]])

    def test_truncated_keeps_leading_cycles(self) -> None:
        case = _case([[0], [1], [2]]).truncated(1)
        assert case.drift_cycles == 1

    def test_truncated_rejects_negative(self) -> None:
        with pytest.raises(ValueError, match=">= 0"):
            _case([[0]]).truncated(-1)


class TestCompactionRequest:
    def test_cycle_zero_has_no_previous_artifact(self) -> None:
        with pytest.raises(ValidationError, match="cycle 0"):
            CompactionRequest(cycle=0, turns=[], previous_artifact=CompactionArtifact())

    def test_later_cycles_need_previous_artifact(self) -> None:
        with pytest.raises(ValidationError, match="needs the previous"):
            CompactionRequest(cycle=1, turns=[])


def test_artifact_accepts_field_names_and_aliases() -> None:
    # Field names work at runtime (populate_by_name); type checkers only see the aliases.
    assert CompactionArtifact(summary_text="a").summary_text == "a"  # pyright: ignore[reportCallIssue]
    assert CompactionArtifact(summaryText="b").summary_text == "b"


def test_add_usage_keeps_none_only_when_both_none() -> None:
    usage = TokenUsage(prompt_tokens=3, completion_tokens=2, call_count=1)
    assert add_usage(None, None) is None
    assert add_usage(None, usage) == usage
    total = add_usage(usage, usage)
    assert total is not None
    assert total.total_tokens == 10
    assert total.call_count == 2
