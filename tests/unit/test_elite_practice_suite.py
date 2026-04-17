"""End-to-end coverage of the elite_practice suite.

Ensures every shipped template parses, passes semantic validation, and
generates successfully at every configured difficulty. Run as unit tests so
every CI build catches a broken template.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from compactbench.dsl import DifficultyLevel, load_suite, validate_template
from compactbench.engine import generate_case

pytestmark = pytest.mark.unit

_ELITE_PRACTICE_DIR = (
    Path(__file__).resolve().parents[2] / "benchmarks" / "public" / "elite_practice"
)

_EXPECTED_FAMILIES: dict[str, int] = {
    "buried_constraint": 5,
    "decision_override": 5,
    "entity_confusion": 5,
}


def test_elite_practice_has_fifteen_templates() -> None:
    templates = load_suite(_ELITE_PRACTICE_DIR)
    assert len(templates) == 15


def test_elite_practice_family_distribution() -> None:
    templates = load_suite(_ELITE_PRACTICE_DIR)
    counts: dict[str, int] = {}
    for t in templates:
        counts[t.family] = counts.get(t.family, 0) + 1
    assert counts == _EXPECTED_FAMILIES


def test_every_elite_practice_template_validates() -> None:
    for template in load_suite(_ELITE_PRACTICE_DIR):
        validate_template(template)


@pytest.mark.parametrize(
    "difficulty",
    [
        DifficultyLevel.EASY,
        DifficultyLevel.MEDIUM,
        DifficultyLevel.HARD,
        DifficultyLevel.ELITE,
    ],
)
def test_every_elite_practice_template_generates(difficulty: DifficultyLevel) -> None:
    for template in load_suite(_ELITE_PRACTICE_DIR):
        case = generate_case(template, seed=11, difficulty=difficulty)
        assert case.case_id
        assert case.transcript.turns
        assert case.evaluation_items


def test_template_keys_are_unique() -> None:
    keys = [t.key for t in load_suite(_ELITE_PRACTICE_DIR)]
    assert len(keys) == len(set(keys))


def test_template_versions_are_all_one_zero_zero() -> None:
    for template in load_suite(_ELITE_PRACTICE_DIR):
        assert template.version == "1.0.0"
