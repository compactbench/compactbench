"""Detect responses that contradict a case's ground truth.

A response "contradicts" when it contains a forbidden-behavior phrase *in a
context where it shouldn't*. Retention-recall items (those whose item type is
``forbidden_behavior_retention`` or ``locked_decision_retention``) are
**excluded** from the denominator — their correct answer names the forbidden
or locked thing, and naming it there is not a contradiction.

This is a conservative lexical detector; genuine semantic contradictions are
caught by the per-item scoring.
"""

from __future__ import annotations

import re

from compactbench.contracts import EvaluationItem, EvaluationItemType, GroundTruth

_WHITESPACE = re.compile(r"\s+")

_RECALL_ITEM_TYPES = frozenset(
    {
        EvaluationItemType.FORBIDDEN_BEHAVIOR_RETENTION,
        EvaluationItemType.LOCKED_DECISION_RETENTION,
    }
)


def _normalize(text: str) -> str:
    return _WHITESPACE.sub(" ", text.strip().lower())


def response_violates(response: str, ground_truth: GroundTruth) -> bool:
    """True if ``response`` contains any forbidden behavior from ``ground_truth``."""
    if not ground_truth.forbidden_behaviors:
        return False
    norm = _normalize(response)
    return any(_normalize(f) in norm for f in ground_truth.forbidden_behaviors)


def count_violations(
    items: list[EvaluationItem],
    responses: dict[str, str],
    ground_truth: GroundTruth,
) -> int:
    """Count responses that violate a forbidden behavior (excluding recall items)."""
    violations = 0
    for item in items:
        if item.item_type in _RECALL_ITEM_TYPES:
            continue
        response = responses.get(item.key, "")
        if response_violates(response, ground_truth):
            violations += 1
    return violations


def contradiction_rate(
    items: list[EvaluationItem],
    responses: dict[str, str],
    ground_truth: GroundTruth,
) -> float:
    """Fraction of non-recall responses that violate a forbidden behavior.

    Denominator is the number of non-recall items. Returns 0.0 when no items
    qualify (e.g., a case made up entirely of recall items).
    """
    non_recall = [i for i in items if i.item_type not in _RECALL_ITEM_TYPES]
    if not non_recall:
        return 0.0
    return count_violations(items, responses, ground_truth) / len(non_recall)
