"""Semantic validator tests.

Pydantic handles structure; these tests cover variable references, generator
existence, and duplicate-name checks.
"""

from __future__ import annotations

from io import StringIO
from pathlib import Path
from typing import Any

import pytest
from ruamel.yaml import YAML

from compactbench.dsl import (
    TemplateValidationError,
    load_suite,
    parse_template_string,
    validate_template,
)

pytestmark = pytest.mark.unit


_yaml = YAML(typ="safe")


def _dump(doc: dict[str, Any]) -> str:
    buf = StringIO()
    _yaml.dump(doc, buf)  # pyright: ignore[reportUnknownMemberType]
    return buf.getvalue()


def _make_template(
    variables: list[dict[str, str]] | None = None,
    transcript_text: str = "hello {{entity}}",
    evaluation_items: list[dict[str, Any]] | None = None,
    ground_truth: dict[str, Any] | None = None,
    difficulty_policy: dict[str, Any] | None = None,
    extra_turns: list[dict[str, Any]] | None = None,
) -> str:
    turns: list[dict[str, Any]] = [{"role": "user", "template": transcript_text}]
    if extra_turns:
        turns.extend(extra_turns)
    doc: dict[str, Any] = {
        "template": {
            "key": "t_v1",
            "family": "t",
            "version": "1.0.0",
            "difficulty_policy": difficulty_policy if difficulty_policy is not None else {},
            "variables": variables
            if variables is not None
            else [{"name": "entity", "generator": "person_name"}],
            "transcript": {"turns": turns},
            "ground_truth": ground_truth if ground_truth is not None else {},
            "evaluation_items": evaluation_items
            if evaluation_items is not None
            else [
                {
                    "key": "q1",
                    "type": "planning_soundness",
                    "prompt": "a prompt",
                    "expected": {"check": "contains_normalized", "value": "x"},
                },
            ],
        }
    }
    return _dump(doc)


def test_valid_template_passes() -> None:
    t = parse_template_string(_make_template())
    validate_template(t)  # no raise


def test_undeclared_reference_raises() -> None:
    t = parse_template_string(_make_template(transcript_text="hello {{nobody}}"))
    with pytest.raises(TemplateValidationError, match="undeclared variable"):
        validate_template(t)


def test_unknown_generator_raises() -> None:
    t = parse_template_string(
        _make_template(variables=[{"name": "entity", "generator": "not_a_real_generator"}])
    )
    with pytest.raises(TemplateValidationError, match="unknown generator"):
        validate_template(t)


def test_duplicate_variable_name_raises() -> None:
    t = parse_template_string(
        _make_template(
            variables=[
                {"name": "entity", "generator": "person_name"},
                {"name": "entity", "generator": "person_name"},
            ]
        )
    )
    with pytest.raises(TemplateValidationError, match="duplicate variable name"):
        validate_template(t)


def test_duplicate_evaluation_item_key_raises() -> None:
    items: list[dict[str, Any]] = [
        {
            "key": "same",
            "type": "planning_soundness",
            "prompt": "p1",
            "expected": {"check": "contains_normalized", "value": "x"},
        },
        {
            "key": "same",
            "type": "planning_soundness",
            "prompt": "p2",
            "expected": {"check": "contains_normalized", "value": "y"},
        },
    ]
    t = parse_template_string(_make_template(evaluation_items=items))
    with pytest.raises(TemplateValidationError, match="duplicate evaluation item key"):
        validate_template(t)


def test_difficulty_reference_is_allowed() -> None:
    t = parse_template_string(
        _make_template(
            difficulty_policy={"distractor_turns": {"easy": 1, "medium": 2, "hard": 3}},
            extra_turns=[
                {"role": "distractor_block", "count": "{{difficulty.distractor_turns}}"},
            ],
        )
    )
    validate_template(t)  # no raise


def test_unknown_difficulty_reference_raises() -> None:
    t = parse_template_string(
        _make_template(transcript_text="{{difficulty.nonsense}}", variables=[])
    )
    with pytest.raises(TemplateValidationError, match="unknown difficulty reference"):
        validate_template(t)


def test_reference_inside_ground_truth_is_checked() -> None:
    t = parse_template_string(
        _make_template(
            variables=[{"name": "a", "generator": "person_name"}],
            transcript_text="hi {{a}}",
            ground_truth={"immutable_facts": ["value: {{missing}}"]},
        )
    )
    with pytest.raises(TemplateValidationError, match="undeclared variable"):
        validate_template(t)


# ---------------------------------------------------------------------------
# Starter templates all pass full validation
# ---------------------------------------------------------------------------


_STARTER_DIR = Path(__file__).resolve().parents[2] / "benchmarks" / "public" / "starter"


def test_all_starter_templates_validate() -> None:
    templates = load_suite(_STARTER_DIR)
    assert len(templates) == 3
    for template in templates:
        validate_template(template)
