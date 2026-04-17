"""Contradiction-rate tests."""

from __future__ import annotations

import pytest

from compactbench.contracts import EvaluationItem, EvaluationItemType, GroundTruth
from compactbench.scoring import (
    contradiction_rate,
    count_violations,
    response_violates,
)

pytestmark = pytest.mark.unit


def _gt(forbidden: list[str]) -> GroundTruth:
    return GroundTruth(forbidden_behaviors=forbidden)


def _item(key: str, item_type: EvaluationItemType) -> EvaluationItem:
    return EvaluationItem(
        key=key, item_type=item_type, prompt="?", expected={"check": "exact", "value": ""}
    )


# --- response_violates (pure lexical) -------------------------------------


def test_response_without_forbidden_does_not_violate() -> None:
    gt = _gt(["deploy on Fridays"])
    assert not response_violates("let's deploy on Wednesday instead", gt)


def test_response_containing_forbidden_violates() -> None:
    gt = _gt(["deploy on Fridays"])
    assert response_violates("we could just deploy on Fridays", gt)


def test_detection_is_case_insensitive() -> None:
    gt = _gt(["use eval()"])
    assert response_violates("let's USE EVAL() here", gt)


def test_detection_is_whitespace_tolerant() -> None:
    gt = _gt(["store passwords in plaintext"])
    assert response_violates("we should  store passwords\n\n in  plaintext", gt)


def test_empty_ground_truth_yields_no_violations() -> None:
    gt = _gt([])
    assert not response_violates("any response", gt)


# --- count_violations (item-aware) ----------------------------------------


def test_count_violations_excludes_recall_items() -> None:
    """A forbidden_behavior_retention item that names the forbidden thing is correct, not a contradiction."""
    gt = _gt(["skip code review"])
    items = [
        _item("recall", EvaluationItemType.FORBIDDEN_BEHAVIOR_RETENTION),
        _item("plan", EvaluationItemType.PLANNING_SOUNDNESS),
    ]
    responses = {
        "recall": "the user said never skip code review",  # names the forbidden → fine
        "plan": "let's skip code review and ship fast",  # proposes forbidden → violation
    }
    assert count_violations(items, responses, gt) == 1


def test_count_violations_counts_non_recall_items_with_forbidden() -> None:
    gt = _gt(["bad action"])
    items = [
        _item("plan", EvaluationItemType.PLANNING_SOUNDNESS),
        _item("entity", EvaluationItemType.ENTITY_INTEGRITY),
    ]
    responses = {
        "plan": "we should perform the bad action",
        "entity": "the subject is acme",
    }
    assert count_violations(items, responses, gt) == 1


def test_count_violations_all_non_recall_responses_clean() -> None:
    gt = _gt(["forbidden"])
    items = [
        _item("plan", EvaluationItemType.PLANNING_SOUNDNESS),
        _item("entity", EvaluationItemType.ENTITY_INTEGRITY),
    ]
    responses = {"plan": "safe plan", "entity": "clean entity"}
    assert count_violations(items, responses, gt) == 0


# --- contradiction_rate ---------------------------------------------------


def test_contradiction_rate_when_empty_responses() -> None:
    gt = _gt(["anything"])
    assert contradiction_rate([], {}, gt) == 0.0


def test_contradiction_rate_when_only_recall_items() -> None:
    gt = _gt(["skip tests"])
    items = [
        _item("r1", EvaluationItemType.FORBIDDEN_BEHAVIOR_RETENTION),
        _item("r2", EvaluationItemType.LOCKED_DECISION_RETENTION),
    ]
    responses = {"r1": "never skip tests", "r2": "the plan is X"}
    # No non-recall items — rate undefined, return 0.
    assert contradiction_rate(items, responses, gt) == 0.0


def test_contradiction_rate_basic_split() -> None:
    gt = _gt(["forbidden"])
    items = [
        _item("plan1", EvaluationItemType.PLANNING_SOUNDNESS),
        _item("plan2", EvaluationItemType.PLANNING_SOUNDNESS),
        _item("entity", EvaluationItemType.ENTITY_INTEGRITY),
        _item("recall", EvaluationItemType.FORBIDDEN_BEHAVIOR_RETENTION),
    ]
    responses = {
        "plan1": "safe plan",
        "plan2": "do the forbidden thing",
        "entity": "clean entity",
        "recall": "the forbidden thing is forbidden",  # recall excluded
    }
    # 1 violation out of 3 non-recall items
    assert contradiction_rate(items, responses, gt) == pytest.approx(1 / 3)


def test_contradiction_rate_full() -> None:
    gt = _gt(["x"])
    items = [_item(f"q{i}", EvaluationItemType.PLANNING_SOUNDNESS) for i in range(4)]
    responses = {item.key: "x is included" for item in items}
    assert contradiction_rate(items, responses, gt) == 1.0
