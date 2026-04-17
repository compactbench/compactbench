"""Evaluation prompt construction + invocation tests."""

from __future__ import annotations

import pytest

from compactbench.contracts import (
    CompactionArtifact,
    EvaluationItem,
    EvaluationItemType,
    StructuredState,
)
from compactbench.providers import MockProvider
from compactbench.runner.evaluation import (
    build_evaluation_prompt,
    evaluate_items,
    render_artifact_for_prompt,
)

pytestmark = pytest.mark.unit


def _artifact(**state_overrides: object) -> CompactionArtifact:
    state = StructuredState(**state_overrides)  # type: ignore[arg-type]
    return CompactionArtifact(
        summaryText="a short summary",
        structured_state=state,
    )


def _item(key: str = "q", prompt: str = "What do you know?") -> EvaluationItem:
    return EvaluationItem(
        key=key,
        item_type=EvaluationItemType.PLANNING_SOUNDNESS,
        prompt=prompt,
        expected={"check": "contains_normalized", "value": "x"},
    )


def test_render_artifact_includes_summary_and_state() -> None:
    artifact = _artifact(
        locked_decisions=["use postgres"],
        forbidden_behaviors=["skip review"],
        entity_map={"Tara": "owner"},
    )
    rendered = render_artifact_for_prompt(artifact)
    assert "a short summary" in rendered
    assert "use postgres" in rendered
    assert "skip review" in rendered
    assert "Tara: owner" in rendered


def test_render_artifact_empty_returns_placeholder() -> None:
    artifact = CompactionArtifact()
    assert "no summary" in render_artifact_for_prompt(artifact).lower()


def test_render_artifact_skips_empty_sections() -> None:
    artifact = _artifact(locked_decisions=["x"])
    rendered = render_artifact_for_prompt(artifact)
    # Should not list sections that are empty.
    assert "Immutable facts" not in rendered
    assert "Forbidden behaviors" not in rendered
    assert "Locked decisions" in rendered


def test_build_evaluation_prompt_contains_question() -> None:
    artifact = _artifact(locked_decisions=["x"])
    item = _item(prompt="What is the plan?")
    prompt = build_evaluation_prompt(artifact, item)
    assert "What is the plan?" in prompt
    assert "ANSWER:" in prompt
    assert "x" in prompt  # the locked decision is in the context


async def test_evaluate_items_issues_one_call_per_item() -> None:
    provider = MockProvider(responses=["alpha", "beta", "gamma"])
    items = [_item("a"), _item("b"), _item("c")]
    artifact = _artifact()
    responses = await evaluate_items(items, artifact, provider, model="m")
    assert responses == {"a": "alpha", "b": "beta", "c": "gamma"}
    assert len(provider.calls) == 3


async def test_evaluate_items_strips_whitespace_from_responses() -> None:
    provider = MockProvider(default="  hello  \n\n")
    responses = await evaluate_items([_item()], _artifact(), provider, model="m")
    assert responses["q"] == "hello"


async def test_evaluate_items_empty_list_makes_no_calls() -> None:
    provider = MockProvider(default="unused")
    responses = await evaluate_items([], _artifact(), provider, model="m")
    assert responses == {}
    assert provider.calls == []
