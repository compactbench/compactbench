"""The extractive and sectioned-summary baselines."""

from __future__ import annotations

import pytest

from compactbench.compactors import ExtractiveCompactor, SectionedSummaryCompactor, get_built_in
from compactbench.contracts import CompactionRequest, Turn, TurnRole
from compactbench.providers.mock import MockProvider
from compactbench.rendering import render_artifact
from compactbench.tokens import count_tokens

pytestmark = pytest.mark.unit


def _turns(*texts: str) -> list[Turn]:
    return [Turn(id=i, role=TurnRole.USER, content=t) for i, t in enumerate(texts)]


async def test_extractive_keeps_state_and_drops_chatter() -> None:
    compactor = ExtractiveCompactor(MockProvider(), "none")
    artifact = await compactor.compact(
        CompactionRequest(
            cycle=0,
            turns=_turns(
                "Morning! Coffee first. We decided to use Postgres for the ledger.",
                "Lovely weather today, isn't it.",
                "PAY-1234 is blocked until the migration lands.",
            ),
            token_budget=2048,
        )
    )
    text = artifact.summary_text
    assert "decided to use Postgres" in text
    assert "PAY-1234 is blocked" in text
    assert "weather" not in text
    assert artifact.method_metadata["calls"] == 0


async def test_extractive_keeps_the_newest_lines_within_budget() -> None:
    compactor = ExtractiveCompactor(MockProvider(), "none")
    turns = _turns(*(f"Decision {i}: we switch the queue to option {i}." for i in range(400)))
    artifact = await compactor.compact(CompactionRequest(cycle=0, turns=turns, token_budget=200))
    assert count_tokens(render_artifact(artifact)) <= 200
    assert "option 399" in artifact.summary_text
    assert "option 0." not in artifact.summary_text
    assert artifact.warnings


async def test_extractive_carries_its_previous_lines() -> None:
    compactor = ExtractiveCompactor(MockProvider(), "none")
    first = await compactor.compact(
        CompactionRequest(cycle=0, turns=_turns("The freeze covers the billing service."))
    )
    second = await compactor.compact(
        CompactionRequest(
            cycle=1, turns=_turns("Owner of search is now Ana."), previous_artifact=first
        )
    )
    assert "freeze covers the billing service" in second.summary_text
    assert "Owner of search" in second.summary_text


async def test_sectioned_summary_is_registered_and_calls_once() -> None:
    assert get_built_in("sectioned-summary") is SectionedSummaryCompactor
    compactor = SectionedSummaryCompactor(MockProvider(), "mock-deterministic")
    artifact = await compactor.compact(CompactionRequest(cycle=0, turns=_turns("Hello.")))
    assert artifact.method_metadata["calls"] == 1
