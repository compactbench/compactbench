"""Contracts round-trip and enforce the artifact schema locked in decisions.md §B2."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from compactbench.contracts import (
    ARTIFACT_SCHEMA_VERSION,
    CompactionArtifact,
    GroundTruth,
    StructuredState,
    Transcript,
    Turn,
    TurnRole,
)

pytestmark = pytest.mark.unit


def test_empty_artifact_is_valid() -> None:
    artifact = CompactionArtifact()
    assert artifact.schema_version == ARTIFACT_SCHEMA_VERSION
    assert artifact.summary_text == ""
    assert artifact.structured_state.immutable_facts == []
    assert artifact.selected_source_turn_ids == []


def test_artifact_rejects_unknown_top_level_fields() -> None:
    with pytest.raises(ValidationError):
        CompactionArtifact.model_validate({"schemaVersion": "1.0.0", "bogus": True})


def test_structured_state_rejects_missing_sections_when_strict() -> None:
    # Populating one section still yields a valid object — all sections default to empty.
    state = StructuredState(locked_decisions=["never ship on Friday"])
    assert state.locked_decisions == ["never ship on Friday"]
    # Unknown section is rejected.
    with pytest.raises(ValidationError):
        StructuredState.model_validate({"made_up_section": []})


def test_transcript_turn_roles() -> None:
    transcript = Transcript(
        turns=[
            Turn(id=0, role=TurnRole.USER, content="hello"),
            Turn(id=1, role=TurnRole.ASSISTANT, content="hi"),
        ]
    )
    assert len(transcript.turns) == 2
    assert transcript.turns[0].role is TurnRole.USER


def test_artifact_accepts_alias_fields() -> None:
    artifact = CompactionArtifact.model_validate(
        {
            "schemaVersion": "1.0.0",
            "summaryText": "short",
            "structured_state": {},
            "selectedSourceTurnIds": [0, 1, 2],
            "warnings": [],
            "methodMetadata": {"k": "v"},
        }
    )
    assert artifact.selected_source_turn_ids == [0, 1, 2]
    assert artifact.method_metadata == {"k": "v"}


def test_ground_truth_accepts_deferred_items() -> None:
    """GroundTruth exposes every bucket the artifact's StructuredState does."""
    gt = GroundTruth(
        deferred_items=["revisit pricing next quarter"],
        unresolved_items=["pick a region"],
    )
    assert gt.deferred_items == ["revisit pricing next quarter"]
    assert gt.unresolved_items == ["pick a region"]


def test_transcript_chars_by_role_sums_content_length() -> None:
    t = Transcript(
        turns=[
            Turn(id=0, role=TurnRole.USER, content="hello"),  # 5
            Turn(id=1, role=TurnRole.ASSISTANT, content="hi world"),  # 8
            Turn(id=2, role=TurnRole.USER, content="ok"),  # 2
        ]
    )
    chars = t.chars_by_role()
    assert chars[TurnRole.USER] == 7
    assert chars[TurnRole.ASSISTANT] == 8
    assert chars[TurnRole.SYSTEM] == 0


def test_transcript_tokens_by_role_uses_caller_tokenizer() -> None:
    """tokens_by_role delegates actual tokenization to the caller's function."""
    t = Transcript(
        turns=[
            Turn(id=0, role=TurnRole.USER, content="hello world"),
            Turn(id=1, role=TurnRole.ASSISTANT, content="hi"),
        ]
    )

    # Naive word-split "tokenizer" — two tokens in the user turn, one in assistant.
    def word_count(text: str) -> int:
        return len(text.split())

    tokens = t.tokens_by_role(word_count)
    assert tokens[TurnRole.USER] == 2
    assert tokens[TurnRole.ASSISTANT] == 1
    assert tokens[TurnRole.SYSTEM] == 0
