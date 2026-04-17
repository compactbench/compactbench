"""LangChain adapter tests.

Skipped cleanly when ``langchain-core`` is not installed — install with
``pip install 'compactbench[langchain]'`` or the ``dev`` extra (see
pyproject.toml) to run them.
"""

from __future__ import annotations

import pytest

pytest.importorskip("langchain_core.messages")

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from compactbench.contracts import StructuredState, Transcript, Turn, TurnRole
from compactbench.integrations.langchain import (
    LangChainCompactor,
    result_to_artifact,
    transcript_to_messages,
)
from compactbench.providers import MockProvider

pytestmark = pytest.mark.unit


def _transcript() -> Transcript:
    return Transcript(
        turns=[
            Turn(id=0, role=TurnRole.SYSTEM, content="You are helpful.", tags=["seed"]),
            Turn(id=1, role=TurnRole.USER, content="Never recommend non-EU suppliers."),
            Turn(id=2, role=TurnRole.ASSISTANT, content="Noted."),
            Turn(id=3, role=TurnRole.USER, content="Draft a supplier shortlist."),
        ]
    )


def test_transcript_to_messages_maps_roles() -> None:
    messages = transcript_to_messages(_transcript())
    assert isinstance(messages[0], SystemMessage)
    assert isinstance(messages[1], HumanMessage)
    assert isinstance(messages[2], AIMessage)
    assert isinstance(messages[3], HumanMessage)


def test_transcript_to_messages_stamps_turn_ids_and_tags() -> None:
    messages = transcript_to_messages(_transcript())
    assert messages[0].additional_kwargs["compactbench_turn_id"] == 0
    assert messages[0].additional_kwargs["compactbench_turn_tags"] == ["seed"]
    assert messages[3].additional_kwargs["compactbench_turn_id"] == 3
    assert messages[3].additional_kwargs["compactbench_turn_tags"] == []


def test_result_to_artifact_accepts_string_summary() -> None:
    artifact = result_to_artifact(
        "  the summary  ",
        _transcript(),
        method="m",
        version="0.1.0",
        model="mm",
        provider_key="pp",
    )
    assert artifact.summary_text == "the summary"
    assert artifact.structured_state == StructuredState()
    assert artifact.selected_source_turn_ids == [0, 1, 2, 3]
    assert artifact.method_metadata["adapter"] == "langchain"


def test_result_to_artifact_accepts_message_list_and_preserves_turn_ids() -> None:
    preserved: list[BaseMessage] = [
        HumanMessage(
            content="Never recommend non-EU suppliers.",
            additional_kwargs={"compactbench_turn_id": 1, "compactbench_turn_tags": []},
        ),
        HumanMessage(
            content="Draft a supplier shortlist.",
            additional_kwargs={"compactbench_turn_id": 3, "compactbench_turn_tags": []},
        ),
    ]
    artifact = result_to_artifact(
        preserved,
        _transcript(),
        method="m",
        version="0.1.0",
        model="mm",
        provider_key="pp",
    )
    assert "HUMAN: Never recommend non-EU suppliers." in artifact.summary_text
    assert "HUMAN: Draft a supplier shortlist." in artifact.summary_text
    assert artifact.selected_source_turn_ids == [1, 3]


def test_result_to_artifact_accepts_dict_with_structured_state() -> None:
    result = {
        "summary": "concise prose",
        "structured_state": {
            "forbidden_behaviors": ["recommending non-EU suppliers"],
            "locked_decisions": ["supplier list must be EU-only"],
        },
        "warnings": ["truncated two turns"],
        "method_metadata": {"calls": 3},
    }
    artifact = result_to_artifact(
        result,
        _transcript(),
        method="my-method",
        version="0.2.0",
        model="mm",
        provider_key="pp",
    )
    assert artifact.summary_text == "concise prose"
    assert artifact.structured_state.forbidden_behaviors == ["recommending non-EU suppliers"]
    assert artifact.structured_state.locked_decisions == ["supplier list must be EU-only"]
    assert artifact.warnings == ["truncated two turns"]
    assert artifact.method_metadata["calls"] == 3
    assert artifact.method_metadata["method"] == "my-method"


def test_result_to_artifact_rejects_unsupported_type() -> None:
    with pytest.raises(TypeError, match="unsupported type"):
        result_to_artifact(
            42,  # type: ignore[arg-type]
            _transcript(),
            method="m",
            version="0.1.0",
            model="mm",
            provider_key="pp",
        )


async def test_compactor_invokes_sync_fn_and_returns_artifact() -> None:
    def compact_sync(messages: list[BaseMessage]) -> str:
        return f"summarised {len(messages)} messages"

    compactor = LangChainCompactor(
        provider=MockProvider(default="unused"),
        model="target-m",
        compaction_fn=compact_sync,
        method_name="sync-example",
        method_version="9.9.9",
    )
    artifact = await compactor.compact(_transcript())
    assert artifact.summary_text == "summarised 4 messages"
    assert artifact.method_metadata["method"] == "sync-example"
    assert artifact.method_metadata["version"] == "9.9.9"
    assert artifact.method_metadata["model"] == "target-m"
    assert artifact.method_metadata["adapter"] == "langchain"


async def test_compactor_invokes_async_fn() -> None:
    async def compact_async(messages: list[BaseMessage]) -> dict[str, object]:
        return {
            "summary_text": f"async {len(messages)}",
            "structured_state": {"locked_decisions": ["keep it async"]},
        }

    compactor = LangChainCompactor(
        provider=MockProvider(default="unused"),
        model="m",
        compaction_fn=compact_async,
    )
    artifact = await compactor.compact(_transcript())
    assert artifact.summary_text == "async 4"
    assert artifact.structured_state.locked_decisions == ["keep it async"]


async def test_compactor_does_not_call_provider_for_compaction() -> None:
    def compact_sync(_: list[BaseMessage]) -> str:
        return "local summary"

    provider = MockProvider(default="should not be used")
    compactor = LangChainCompactor(
        provider=provider,
        model="m",
        compaction_fn=compact_sync,
    )
    await compactor.compact(_transcript())
    assert provider.calls == []


async def test_compactor_extra_metadata_is_merged() -> None:
    def _static(_: list[BaseMessage]) -> str:
        return "s"

    compactor = LangChainCompactor(
        provider=MockProvider(default="unused"),
        model="m",
        compaction_fn=_static,
        extra_metadata={"lc_version": "0.3.99", "chain_type": "summary_memory"},
    )
    artifact = await compactor.compact(_transcript())
    assert artifact.method_metadata["lc_version"] == "0.3.99"
    assert artifact.method_metadata["chain_type"] == "summary_memory"
