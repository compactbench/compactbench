"""Hybrid-ledger compactor tests: append-only accumulation across cycles."""

from __future__ import annotations

import json

import pytest

from compactbench.compactors import HybridLedgerCompactor
from compactbench.contracts import Transcript, Turn, TurnRole
from compactbench.providers import MockProvider

pytestmark = pytest.mark.unit


def _transcript() -> Transcript:
    return Transcript(
        turns=[
            Turn(id=0, role=TurnRole.USER, content="Plan the pricing revamp with Priya."),
            Turn(id=1, role=TurnRole.ASSISTANT, content="Got it."),
        ]
    )


def _delta_json(**overrides: object) -> str:
    state: dict[str, object] = {
        "immutable_facts": [],
        "locked_decisions": [],
        "deferred_items": [],
        "forbidden_behaviors": [],
        "entity_map": {},
        "unresolved_items": [],
    }
    state.update(overrides)
    return json.dumps(state)


async def test_first_cycle_has_no_previous_to_merge() -> None:
    provider = MockProvider(
        responses=[
            _delta_json(
                locked_decisions=["use postgres"],
                forbidden_behaviors=["skip review"],
            ),
            "Situational header.",
        ]
    )
    compactor = HybridLedgerCompactor(provider, model="m")
    artifact = await compactor.compact(_transcript())
    assert artifact.summary_text == "Situational header."
    assert artifact.structured_state.locked_decisions == ["use postgres"]
    assert artifact.structured_state.forbidden_behaviors == ["skip review"]
    assert artifact.method_metadata["cycles_accumulated"] == 1


async def test_second_cycle_appends_new_items() -> None:
    provider = MockProvider(
        responses=[
            _delta_json(locked_decisions=["use postgres"], forbidden_behaviors=["skip review"]),
            "Cycle 1 header.",
            _delta_json(
                locked_decisions=["deploy behind a flag"], forbidden_behaviors=["mutate on Friday"]
            ),
            "Cycle 2 header.",
        ]
    )
    compactor = HybridLedgerCompactor(provider, model="m")
    first = await compactor.compact(_transcript())
    second = await compactor.compact(_transcript(), previous_artifact=first)
    # Append-only sections accumulate.
    assert second.structured_state.locked_decisions == ["use postgres", "deploy behind a flag"]
    assert second.structured_state.forbidden_behaviors == ["skip review", "mutate on Friday"]
    assert second.method_metadata["cycles_accumulated"] == 2


async def test_duplicates_are_deduplicated() -> None:
    provider = MockProvider(
        responses=[
            _delta_json(locked_decisions=["reuse auth flow"]),
            "h1",
            _delta_json(locked_decisions=["reuse auth flow"]),  # repeat
            "h2",
        ]
    )
    compactor = HybridLedgerCompactor(provider, model="m")
    first = await compactor.compact(_transcript())
    second = await compactor.compact(_transcript(), previous_artifact=first)
    assert second.structured_state.locked_decisions == ["reuse auth flow"]


async def test_entity_map_merges_with_new_winning() -> None:
    provider = MockProvider(
        responses=[
            _delta_json(entity_map={"Priya": "pm", "Rafael": "eng"}),
            "h1",
            _delta_json(entity_map={"Priya": "lead", "Sofia": "design"}),  # Priya role updated
            "h2",
        ]
    )
    compactor = HybridLedgerCompactor(provider, model="m")
    first = await compactor.compact(_transcript())
    second = await compactor.compact(_transcript(), previous_artifact=first)
    assert second.structured_state.entity_map == {
        "Priya": "lead",
        "Rafael": "eng",
        "Sofia": "design",
    }


async def test_issues_two_calls_per_compact() -> None:
    provider = MockProvider(responses=[_delta_json(), "header1", _delta_json(), "header2"])
    compactor = HybridLedgerCompactor(provider, model="m")
    await compactor.compact(_transcript())
    assert len(provider.calls) == 2
    await compactor.compact(_transcript())
    assert len(provider.calls) == 4
