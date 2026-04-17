"""Naive-summary baseline tests."""

from __future__ import annotations

import pytest

from compactbench.compactors import NaiveSummaryCompactor
from compactbench.contracts import Transcript, Turn, TurnRole
from compactbench.providers import MockProvider

pytestmark = pytest.mark.unit


def _transcript() -> Transcript:
    return Transcript(
        turns=[
            Turn(id=0, role=TurnRole.USER, content="plan the pricing revamp"),
            Turn(id=1, role=TurnRole.ASSISTANT, content="sure"),
        ]
    )


async def test_uses_provider_response_as_summary_text() -> None:
    provider = MockProvider(default="the summary")
    compactor = NaiveSummaryCompactor(provider, model="m")
    artifact = await compactor.compact(_transcript())
    assert artifact.summary_text == "the summary"


async def test_leaves_structured_state_empty() -> None:
    provider = MockProvider(default="summary")
    compactor = NaiveSummaryCompactor(provider, model="m")
    artifact = await compactor.compact(_transcript())
    state = artifact.structured_state
    assert state.immutable_facts == []
    assert state.locked_decisions == []
    assert state.deferred_items == []
    assert state.forbidden_behaviors == []
    assert state.entity_map == {}
    assert state.unresolved_items == []


async def test_strips_whitespace_from_summary() -> None:
    provider = MockProvider(default="\n\n  the summary  \n")
    compactor = NaiveSummaryCompactor(provider, model="m")
    artifact = await compactor.compact(_transcript())
    assert artifact.summary_text == "the summary"


async def test_issues_exactly_one_provider_call() -> None:
    provider = MockProvider(default="x")
    compactor = NaiveSummaryCompactor(provider, model="m")
    await compactor.compact(_transcript())
    assert len(provider.calls) == 1


async def test_prompt_includes_conversation_content() -> None:
    provider = MockProvider(default="x")
    compactor = NaiveSummaryCompactor(provider, model="m")
    await compactor.compact(_transcript())
    prompt = provider.calls[0].prompt
    assert "plan the pricing revamp" in prompt
    assert "USER" in prompt
