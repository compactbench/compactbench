"""End-to-end scorer tests using real starter-suite cases."""

from __future__ import annotations

from pathlib import Path

import pytest

from compactbench.contracts import (
    CompactionArtifact,
    EvaluationItem,
    EvaluationItemType,
    GeneratedCase,
    GroundTruth,
    StructuredState,
    Transcript,
    Turn,
    TurnRole,
)
from compactbench.dsl import DifficultyLevel, parse_template_file
from compactbench.engine import generate_case
from compactbench.scoring import WEIGHTS, score_cycle, score_item

pytestmark = pytest.mark.unit


_STARTER_DIR = Path(__file__).resolve().parents[2] / "benchmarks" / "public" / "starter"


# ---------------------------------------------------------------------------
# Single-item scoring
# ---------------------------------------------------------------------------


def _item(key: str, item_type: EvaluationItemType, check_spec: dict[str, object]) -> EvaluationItem:
    return EvaluationItem(key=key, item_type=item_type, prompt="?", expected=check_spec)


def test_score_item_on_passing_response() -> None:
    item = _item(
        "q",
        EvaluationItemType.IMMUTABLE_FACT_RECALL,
        {"check": "contains_normalized", "value": "Tara"},
    )
    result = score_item(item, "The subject is Tara.")
    assert result.score == 1.0
    assert result.weight == WEIGHTS[EvaluationItemType.IMMUTABLE_FACT_RECALL]
    assert result.item_type == "immutable_fact_recall"
    assert result.check_type == "contains_normalized"


def test_score_item_on_failing_response() -> None:
    item = _item(
        "q",
        EvaluationItemType.LOCKED_DECISION_RETENTION,
        {"check": "contains_normalized", "value": "approved_plan"},
    )
    result = score_item(item, "completely unrelated response")
    assert result.score == 0.0
    assert result.weight == 3.0


# ---------------------------------------------------------------------------
# Full-case scoring
# ---------------------------------------------------------------------------


def _minimal_case(
    evaluation_items: list[EvaluationItem], ground_truth: GroundTruth | None = None
) -> GeneratedCase:
    return GeneratedCase(
        case_id="test:s0:dmedium",
        template_key="test_template",
        template_version="1.0.0",
        seed=0,
        difficulty="medium",
        transcript=Transcript(turns=[Turn(id=0, role=TurnRole.USER, content="hi")]),
        ground_truth=ground_truth or GroundTruth(),
        evaluation_items=evaluation_items,
    )


def _empty_artifact() -> CompactionArtifact:
    return CompactionArtifact(summaryText="summary", structured_state=StructuredState())


def test_all_pass_yields_cycle_score_one() -> None:
    items = [
        _item(
            "q1",
            EvaluationItemType.IMMUTABLE_FACT_RECALL,
            {"check": "contains_normalized", "value": "hello"},
        ),
        _item(
            "q2",
            EvaluationItemType.ENTITY_INTEGRITY,
            {"check": "contains_normalized", "value": "hello"},
        ),
    ]
    case = _minimal_case(items)
    sc = score_cycle(case, _empty_artifact(), {"q1": "hello world", "q2": "hello there"})
    assert sc.cycle_score == 1.0
    assert sc.contradiction_rate == 0.0
    assert sc.penalized_cycle_score == 1.0


def test_all_fail_yields_cycle_score_zero() -> None:
    items = [
        _item(
            "q1",
            EvaluationItemType.IMMUTABLE_FACT_RECALL,
            {"check": "contains_normalized", "value": "hello"},
        ),
    ]
    case = _minimal_case(items)
    sc = score_cycle(case, _empty_artifact(), {"q1": "nope"})
    assert sc.cycle_score == 0.0
    assert sc.penalized_cycle_score == 0.0


def test_weighted_aggregation() -> None:
    # weight 3 (fail) + weight 1 (pass) → (3 * 0 + 1 * 1) / 4 = 0.25
    items = [
        _item(
            "q_heavy",
            EvaluationItemType.LOCKED_DECISION_RETENTION,
            {"check": "contains_normalized", "value": "heavy_answer"},
        ),
        _item(
            "q_light",
            EvaluationItemType.ENTITY_INTEGRITY,
            {"check": "contains_normalized", "value": "light"},
        ),
    ]
    case = _minimal_case(items)
    sc = score_cycle(case, _empty_artifact(), {"q_heavy": "missing", "q_light": "light here"})
    assert sc.cycle_score == pytest.approx(0.25)


def test_contradiction_penalty_applied() -> None:
    items = [
        _item(
            "q",
            EvaluationItemType.ENTITY_INTEGRITY,
            {"check": "contains_normalized", "value": "x"},
        ),
    ]
    gt = GroundTruth(forbidden_behaviors=["forbidden"])
    case = _minimal_case(items, ground_truth=gt)
    # response contains both 'x' (passes) AND 'forbidden' (violates).
    sc = score_cycle(case, _empty_artifact(), {"q": "x and forbidden together"})
    assert sc.cycle_score == 1.0
    assert sc.contradiction_rate == 1.0
    assert sc.penalized_cycle_score == 0.0


def test_empty_evaluation_items_yields_zero_cycle_score() -> None:
    case = _minimal_case([])
    sc = score_cycle(case, _empty_artifact(), {})
    assert sc.cycle_score == 0.0
    assert sc.contradiction_rate == 0.0


def test_missing_response_counts_as_fail() -> None:
    items = [
        _item(
            "q",
            EvaluationItemType.PLANNING_SOUNDNESS,
            {"check": "contains_normalized", "value": "x"},
        ),
    ]
    case = _minimal_case(items)
    sc = score_cycle(case, _empty_artifact(), {})  # no response provided
    assert sc.cycle_score == 0.0


def test_cycle_number_is_preserved() -> None:
    items = [
        _item(
            "q", EvaluationItemType.ENTITY_INTEGRITY, {"check": "contains_normalized", "value": "x"}
        )
    ]
    case = _minimal_case(items)
    sc = score_cycle(case, _empty_artifact(), {"q": "x"}, cycle_number=2)
    assert sc.cycle_number == 2


def test_negative_cycle_number_raises() -> None:
    items = [
        _item(
            "q", EvaluationItemType.ENTITY_INTEGRITY, {"check": "contains_normalized", "value": "x"}
        )
    ]
    case = _minimal_case(items)
    with pytest.raises(ValueError, match=">= 0"):
        score_cycle(case, _empty_artifact(), {"q": "x"}, cycle_number=-1)


# ---------------------------------------------------------------------------
# Integration with the real starter suite
# ---------------------------------------------------------------------------


def test_scores_real_starter_case_with_perfect_responses() -> None:
    """Generate a real case, construct ideal responses from ground truth, score 1.0."""
    template = parse_template_file(_STARTER_DIR / "buried_constraint_starter_v1.yaml")
    case = generate_case(template, seed=42, difficulty=DifficultyLevel.MEDIUM)
    # Perfect responses: repeat each expected value verbatim.
    responses = {item.key: str(item.expected.get("value", "")) for item in case.evaluation_items}
    # forbidden_absent items should have a response that does NOT include the forbidden phrase.
    for item in case.evaluation_items:
        if item.expected.get("check") == "forbidden_absent":
            responses[item.key] = "clean unrelated response text"
    artifact = CompactionArtifact(
        summaryText="short summary",
        structured_state=StructuredState(
            forbidden_behaviors=list(case.ground_truth.forbidden_behaviors),
            entity_map=dict(case.ground_truth.entity_map),
        ),
    )
    sc = score_cycle(case, artifact, responses)
    assert sc.cycle_score == 1.0
    assert sc.contradiction_rate == 0.0
    assert sc.penalized_cycle_score == 1.0
    assert sc.compression_ratio > 0


def test_scores_real_starter_case_with_empty_responses() -> None:
    template = parse_template_file(_STARTER_DIR / "buried_constraint_starter_v1.yaml")
    case = generate_case(template, seed=42, difficulty=DifficultyLevel.MEDIUM)
    artifact = CompactionArtifact(summaryText="unrelated")
    responses = {item.key: "" for item in case.evaluation_items}
    sc = score_cycle(case, artifact, responses)
    # Every contains_normalized expects a value that isn't in empty response → 0.
    # forbidden_absent on empty response → 1.0 (absent by virtue of emptiness).
    # So cycle_score is positive only from forbidden_absent items.
    assert 0.0 <= sc.cycle_score <= 1.0
    assert sc.cycle_score < 1.0  # not everything passed
