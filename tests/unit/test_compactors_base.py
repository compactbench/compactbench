"""Compactor ABC + registry tests (shared across all built-ins)."""

from __future__ import annotations

import re

import pytest

from compactbench.compactors import (
    Compactor,
    HierarchicalSummaryCompactor,
    HybridLedgerCompactor,
    NaiveSummaryCompactor,
    StructuredStateCompactor,
    UnknownCompactorError,
    get_built_in,
    list_built_ins,
)
from compactbench.contracts import ARTIFACT_SCHEMA_VERSION, Transcript, Turn, TurnRole
from compactbench.providers import MockProvider

pytestmark = pytest.mark.unit

_PLACEHOLDER = re.compile(r"\{\{[^}]+\}\}")


_ALL_COMPACTORS = [
    NaiveSummaryCompactor,
    StructuredStateCompactor,
    HierarchicalSummaryCompactor,
    HybridLedgerCompactor,
]


def _minimal_transcript() -> Transcript:
    return Transcript(
        turns=[
            Turn(id=0, role=TurnRole.USER, content="Plan the auth rewrite with Tara."),
            Turn(id=1, role=TurnRole.ASSISTANT, content="Sure. What constraints?"),
            Turn(id=2, role=TurnRole.USER, content="Never skip code review."),
        ]
    )


def _valid_state_json() -> str:
    return (
        '{"immutable_facts": ["topic: auth rewrite"],'
        ' "locked_decisions": [],'
        ' "deferred_items": [],'
        ' "forbidden_behaviors": ["skip code review"],'
        ' "entity_map": {"Tara": "primary"},'
        ' "unresolved_items": []}'
    )


def _mock_for(compactor_cls: type[Compactor]) -> MockProvider:
    """Return a mock provider primed with plausible responses for each compactor."""
    name = compactor_cls.name
    if name == "naive-summary":
        return MockProvider(default="A short prose summary of the conversation.")
    if name == "structured-state":
        return MockProvider(default=_valid_state_json())
    if name == "hierarchical-summary":
        # One chunk → chunk summary + state. (transcript is 3 turns, below CHUNK_SIZE of 10.)
        return MockProvider(responses=["chunk summary"], default=_valid_state_json())
    if name == "hybrid-ledger":
        # Two calls per compact: delta JSON then header.
        return MockProvider(responses=[_valid_state_json(), "Situational header."])
    raise AssertionError(f"no mock wiring for {name!r}")


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_list_built_ins_includes_required_four() -> None:
    expected = {"naive-summary", "structured-state", "hierarchical-summary", "hybrid-ledger"}
    assert expected.issubset(set(list_built_ins()))


def test_get_built_in_returns_class() -> None:
    assert get_built_in("hybrid-ledger") is HybridLedgerCompactor


def test_get_built_in_raises_on_unknown() -> None:
    with pytest.raises(UnknownCompactorError):
        get_built_in("not-a-method")


# ---------------------------------------------------------------------------
# Shape invariants — every compactor, every compaction
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("compactor_cls", _ALL_COMPACTORS)
async def test_compactor_returns_valid_artifact(compactor_cls: type[Compactor]) -> None:
    provider = _mock_for(compactor_cls)
    compactor = compactor_cls(provider, model="mock-m")
    artifact = await compactor.compact(_minimal_transcript())
    assert artifact.schema_version == ARTIFACT_SCHEMA_VERSION
    assert isinstance(artifact.summary_text, str)
    # Every structured section is present (empty OK, missing NOT OK — pydantic would have raised)
    _ = artifact.structured_state.immutable_facts
    _ = artifact.structured_state.locked_decisions
    _ = artifact.structured_state.deferred_items
    _ = artifact.structured_state.forbidden_behaviors
    _ = artifact.structured_state.entity_map
    _ = artifact.structured_state.unresolved_items


@pytest.mark.parametrize("compactor_cls", _ALL_COMPACTORS)
async def test_compactor_emits_no_unresolved_placeholders(
    compactor_cls: type[Compactor],
) -> None:
    provider = _mock_for(compactor_cls)
    compactor = compactor_cls(provider, model="mock-m")
    artifact = await compactor.compact(_minimal_transcript())
    serialized = artifact.model_dump_json()
    assert not _PLACEHOLDER.search(serialized)


@pytest.mark.parametrize("compactor_cls", _ALL_COMPACTORS)
async def test_compactor_records_selected_turn_ids(
    compactor_cls: type[Compactor],
) -> None:
    provider = _mock_for(compactor_cls)
    compactor = compactor_cls(provider, model="mock-m")
    transcript = _minimal_transcript()
    artifact = await compactor.compact(transcript)
    assert artifact.selected_source_turn_ids == [t.id for t in transcript.turns]


@pytest.mark.parametrize("compactor_cls", _ALL_COMPACTORS)
async def test_compactor_records_method_metadata(compactor_cls: type[Compactor]) -> None:
    provider = _mock_for(compactor_cls)
    compactor = compactor_cls(provider, model="mock-m")
    artifact = await compactor.compact(_minimal_transcript())
    meta = artifact.method_metadata
    assert meta["method"] == compactor_cls.name
    assert meta["version"] == compactor_cls.version
    assert meta["model"] == "mock-m"
    assert meta["provider"] == "mock"
    assert meta["calls"] >= 1
