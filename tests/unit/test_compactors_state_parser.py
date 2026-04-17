"""Shared JSON → StructuredState parser tests."""

from __future__ import annotations

import json

import pytest

from compactbench.compactors._state_parser import parse_state

pytestmark = pytest.mark.unit


def _all_sections(**overrides: object) -> str:
    doc: dict[str, object] = {
        "immutable_facts": [],
        "locked_decisions": [],
        "deferred_items": [],
        "forbidden_behaviors": [],
        "entity_map": {},
        "unresolved_items": [],
    }
    doc.update(overrides)
    return json.dumps(doc)


def test_fully_populated_state() -> None:
    text = _all_sections(
        locked_decisions=["use postgres"],
        forbidden_behaviors=["skip review"],
        entity_map={"Tara": "owner"},
    )
    state, warnings = parse_state(text)
    assert warnings == []
    assert state.locked_decisions == ["use postgres"]
    assert state.forbidden_behaviors == ["skip review"]
    assert state.entity_map == {"Tara": "owner"}


def test_strips_json_code_fence() -> None:
    wrapped = "```json\n" + _all_sections(locked_decisions=["x"]) + "\n```"
    state, warnings = parse_state(wrapped)
    assert warnings == []
    assert state.locked_decisions == ["x"]


def test_strips_bare_code_fence() -> None:
    wrapped = "```\n" + _all_sections(locked_decisions=["x"]) + "\n```"
    state, _warnings = parse_state(wrapped)
    assert state.locked_decisions == ["x"]


def test_missing_sections_become_empty() -> None:
    # Only one section provided; others default to empty.
    state, warnings = parse_state('{"locked_decisions": ["x"]}')
    assert state.locked_decisions == ["x"]
    assert state.immutable_facts == []
    assert state.entity_map == {}
    assert warnings == []


def test_invalid_json_warns_and_returns_empty() -> None:
    state, warnings = parse_state("not valid json at all")
    assert state.locked_decisions == []
    assert any("JSON" in w for w in warnings)


def test_non_object_root_warns() -> None:
    state, warnings = parse_state('["not", "an", "object"]')
    assert state.locked_decisions == []
    assert any("object" in w for w in warnings)


def test_non_list_section_dropped_with_warning() -> None:
    text = '{"locked_decisions": "not a list"}'
    state, warnings = parse_state(text)
    assert state.locked_decisions == []
    assert any("locked_decisions" in w for w in warnings)


def test_non_string_items_filtered() -> None:
    text = '{"locked_decisions": ["valid", 42, null, "also valid"]}'
    state, warnings = parse_state(text)
    assert state.locked_decisions == ["valid", "also valid"]
    assert len(warnings) >= 1


def test_empty_strings_stripped() -> None:
    text = '{"locked_decisions": ["real", "   ", ""]}'
    state, _ = parse_state(text)
    assert state.locked_decisions == ["real"]


def test_entity_map_non_dict_dropped() -> None:
    text = '{"entity_map": ["list", "not", "map"]}'
    state, warnings = parse_state(text)
    assert state.entity_map == {}
    assert any("entity_map" in w for w in warnings)


def test_entity_map_non_string_values_skipped() -> None:
    text = '{"entity_map": {"Tara": "owner", "Bob": 42}}'
    state, warnings = parse_state(text)
    assert state.entity_map == {"Tara": "owner"}
    assert len(warnings) >= 1


def test_oversized_strings_truncated() -> None:
    long = "x" * 1000
    text = json.dumps({"locked_decisions": [long]})
    state, warnings = parse_state(text)
    assert len(state.locked_decisions[0]) == 500
    assert any("truncating" in w.lower() for w in warnings)
