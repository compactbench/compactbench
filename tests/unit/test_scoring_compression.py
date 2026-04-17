"""Compression-ratio tests."""

from __future__ import annotations

import pytest

from compactbench.contracts import (
    CompactionArtifact,
    StructuredState,
    Transcript,
    Turn,
    TurnRole,
)
from compactbench.scoring import (
    artifact_tokens,
    compression_ratio,
    count_tokens,
    transcript_tokens,
)

pytestmark = pytest.mark.unit


def test_count_tokens_empty_is_zero() -> None:
    assert count_tokens("") == 0


def test_count_tokens_nonempty_is_positive() -> None:
    assert count_tokens("hello world") > 0


def test_cl100k_hello_world_is_two_tokens() -> None:
    # Spot-check: "hello world" under cl100k_base is exactly 2 tokens.
    assert count_tokens("hello world") == 2


def test_transcript_tokens_sums_over_turns() -> None:
    t = Transcript(
        turns=[
            Turn(id=0, role=TurnRole.USER, content="hello world"),
            Turn(id=1, role=TurnRole.ASSISTANT, content="hello world"),
        ]
    )
    assert transcript_tokens(t) == 4


def test_artifact_tokens_counts_summary_and_state() -> None:
    artifact = CompactionArtifact(
        summaryText="hello world",
        structured_state=StructuredState(
            immutable_facts=["hello world"],
            locked_decisions=["hello world"],
        ),
    )
    assert artifact_tokens(artifact) == 6


def test_compression_ratio_basic() -> None:
    # 40 transcript tokens, 2 artifact tokens = 20x compression.
    # Use a known content to keep the test deterministic.
    content = "hello world " * 20  # approximately 40 tokens
    transcript = Transcript(turns=[Turn(id=0, role=TurnRole.USER, content=content.strip())])
    artifact = CompactionArtifact(summaryText="hello world")
    ratio = compression_ratio(transcript, artifact)
    assert ratio == pytest.approx(transcript_tokens(transcript) / 2)


def test_compression_ratio_empty_artifact_does_not_divide_by_zero() -> None:
    transcript = Transcript(turns=[Turn(id=0, role=TurnRole.USER, content="hello world")])
    artifact = CompactionArtifact()  # all empty
    # dst floored at 1 to keep ratio finite
    ratio = compression_ratio(transcript, artifact)
    assert ratio == transcript_tokens(transcript)


def test_compression_ratio_empty_transcript_is_zero() -> None:
    transcript = Transcript(turns=[])
    artifact = CompactionArtifact(summaryText="anything")
    assert compression_ratio(transcript, artifact) == 0.0


def test_compression_ratio_is_finite() -> None:
    transcript = Transcript(turns=[Turn(id=0, role=TurnRole.USER, content="x" * 100)])
    artifact = CompactionArtifact(summaryText="y")
    ratio = compression_ratio(transcript, artifact)
    assert 0.0 <= ratio < float("inf")
