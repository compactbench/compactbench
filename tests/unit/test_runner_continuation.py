"""Drift-cycle continuation tests."""

from __future__ import annotations

import pytest

from compactbench.contracts import (
    CompactionArtifact,
    StructuredState,
    Transcript,
    Turn,
    TurnRole,
)
from compactbench.providers import MockProvider
from compactbench.runner.continuation import (
    build_continuation_prompt,
    extend_with_continuation,
    select_continuation_prompt,
)

pytestmark = pytest.mark.unit


def _artifact() -> CompactionArtifact:
    return CompactionArtifact(
        summaryText="situational context",
        structured_state=StructuredState(locked_decisions=["use postgres"]),
    )


def _transcript(n: int = 3) -> Transcript:
    return Transcript(
        turns=[
            Turn(id=i, role=TurnRole.USER if i % 2 == 0 else TurnRole.ASSISTANT, content=f"t{i}")
            for i in range(n)
        ]
    )


def test_select_continuation_prompt_is_deterministic() -> None:
    a = select_continuation_prompt(case_seed=42, cycle_number=1)
    b = select_continuation_prompt(case_seed=42, cycle_number=1)
    assert a == b


def test_select_continuation_prompt_varies_by_cycle() -> None:
    prompts = {select_continuation_prompt(case_seed=42, cycle_number=n) for n in range(5)}
    # Probabilistic: >1 distinct out of 5 picks from an 8-element pool.
    assert len(prompts) > 1


def test_build_continuation_prompt_includes_context_and_user() -> None:
    prompt = build_continuation_prompt(_artifact(), "what next?")
    assert "situational context" in prompt
    assert "use postgres" in prompt
    assert "what next?" in prompt
    assert "ASSISTANT:" in prompt


async def test_extend_adds_two_turns() -> None:
    provider = MockProvider(default="assistant reply")
    start = _transcript(3)
    extended = await extend_with_continuation(
        start, _artifact(), provider, "m", case_seed=42, cycle_number=1
    )
    assert len(extended.turns) == 5
    user_turn, assistant_turn = extended.turns[-2:]
    assert user_turn.role is TurnRole.USER
    assert assistant_turn.role is TurnRole.ASSISTANT
    assert assistant_turn.content == "assistant reply"


async def test_extended_turn_ids_are_contiguous() -> None:
    provider = MockProvider(default="reply")
    start = _transcript(3)
    extended = await extend_with_continuation(
        start, _artifact(), provider, "m", case_seed=42, cycle_number=1
    )
    ids = [t.id for t in extended.turns]
    assert ids == list(range(len(ids)))


async def test_continuation_turns_tagged() -> None:
    provider = MockProvider(default="reply")
    extended = await extend_with_continuation(
        _transcript(2), _artifact(), provider, "m", case_seed=1, cycle_number=1
    )
    for t in extended.turns[-2:]:
        assert "continuation" in t.tags


async def test_provider_prompt_references_previous_artifact() -> None:
    provider = MockProvider(default="reply")
    await extend_with_continuation(
        _transcript(2), _artifact(), provider, "m", case_seed=1, cycle_number=1
    )
    assert provider.calls, "expected provider to have been called"
    prompt = provider.calls[0].prompt
    assert "use postgres" in prompt  # locked decision from previous artifact
    assert "situational context" in prompt
