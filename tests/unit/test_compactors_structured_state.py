"""Structured-state baseline tests."""

from __future__ import annotations

import json

import pytest

from compactbench.compactors import StructuredStateCompactor
from compactbench.contracts import Transcript, Turn, TurnRole
from compactbench.providers import MockProvider

pytestmark = pytest.mark.unit


def _transcript() -> Transcript:
    return Transcript(turns=[Turn(id=0, role=TurnRole.USER, content="hi")])


def _complete_state_json(**overrides: object) -> str:
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


async def test_populates_state_from_json_response() -> None:
    response = _complete_state_json(
        locked_decisions=["use postgres"],
        forbidden_behaviors=["skip review"],
        entity_map={"Alice": "owner"},
    )
    provider = MockProvider(default=response)
    compactor = StructuredStateCompactor(provider, model="m")
    artifact = await compactor.compact(_transcript())
    assert artifact.structured_state.locked_decisions == ["use postgres"]
    assert artifact.structured_state.forbidden_behaviors == ["skip review"]
    assert artifact.structured_state.entity_map == {"Alice": "owner"}


async def test_summary_text_is_empty() -> None:
    provider = MockProvider(default=_complete_state_json())
    compactor = StructuredStateCompactor(provider, model="m")
    artifact = await compactor.compact(_transcript())
    assert artifact.summary_text == ""


async def test_requests_json_response_format() -> None:
    provider = MockProvider(default=_complete_state_json())
    compactor = StructuredStateCompactor(provider, model="m")
    await compactor.compact(_transcript())
    assert provider.calls[0].response_format == {"type": "json_object"}


async def test_invalid_json_populates_warnings_and_empty_state() -> None:
    provider = MockProvider(default="garbage output not json")
    compactor = StructuredStateCompactor(provider, model="m")
    artifact = await compactor.compact(_transcript())
    assert artifact.warnings
    assert artifact.structured_state.locked_decisions == []
