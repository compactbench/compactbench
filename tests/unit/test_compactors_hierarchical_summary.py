"""Hierarchical-summary compactor tests."""

from __future__ import annotations

import json

import pytest

from compactbench.compactors import HierarchicalSummaryCompactor
from compactbench.contracts import Transcript, Turn, TurnRole
from compactbench.providers import MockProvider

pytestmark = pytest.mark.unit


def _complete_state_json() -> str:
    return json.dumps(
        {
            "immutable_facts": [],
            "locked_decisions": [],
            "deferred_items": [],
            "forbidden_behaviors": [],
            "entity_map": {},
            "unresolved_items": [],
        }
    )


def _transcript_of(n: int) -> Transcript:
    return Transcript(
        turns=[
            Turn(
                id=i,
                role=TurnRole.USER if i % 2 == 0 else TurnRole.ASSISTANT,
                content=f"turn {i}",
            )
            for i in range(n)
        ]
    )


async def test_single_chunk_skips_meta_call() -> None:
    # Transcript smaller than CHUNK_SIZE (10) => 1 chunk, no meta pass.
    # Provider sees: 1 chunk call + 1 state call = 2 total.
    provider = MockProvider(responses=["chunk summary", _complete_state_json()])
    compactor = HierarchicalSummaryCompactor(provider, model="m")
    artifact = await compactor.compact(_transcript_of(5))
    assert len(provider.calls) == 2
    assert artifact.summary_text == "chunk summary"
    assert artifact.method_metadata["chunks"] == 1


async def test_multi_chunk_runs_meta_call() -> None:
    # 25 turns with CHUNK_SIZE=10 => 3 chunks.
    # Calls: 3 chunk summaries + 1 meta summary + 1 state call = 5 total.
    provider = MockProvider(
        responses=[
            "summary 0",
            "summary 1",
            "summary 2",
            "final combined summary",
            _complete_state_json(),
        ]
    )
    compactor = HierarchicalSummaryCompactor(provider, model="m")
    artifact = await compactor.compact(_transcript_of(25))
    assert len(provider.calls) == 5
    assert artifact.summary_text == "final combined summary"
    assert artifact.method_metadata["chunks"] == 3


async def test_state_call_requests_json_format() -> None:
    provider = MockProvider(responses=["chunk summary", _complete_state_json()])
    compactor = HierarchicalSummaryCompactor(provider, model="m")
    await compactor.compact(_transcript_of(5))
    # The last call is the state call.
    assert provider.calls[-1].response_format == {"type": "json_object"}


async def test_chunk_prompt_includes_turn_content() -> None:
    provider = MockProvider(responses=["chunk summary", _complete_state_json()])
    compactor = HierarchicalSummaryCompactor(provider, model="m")
    await compactor.compact(_transcript_of(5))
    chunk_prompt = provider.calls[0].prompt
    assert "turn 0" in chunk_prompt
    assert "USER" in chunk_prompt
