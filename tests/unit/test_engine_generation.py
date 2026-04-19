"""End-to-end case generation tests."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from compactbench.contracts import TurnRole
from compactbench.dsl import (
    DifficultyLevel,
    TemplateDefinition,
    load_suite,
    parse_template_file,
)
from compactbench.engine import (
    GenerationError,
    generate_case,
)

pytestmark = pytest.mark.unit


_STARTER_DIR = Path(__file__).resolve().parents[2] / "benchmarks" / "public" / "starter"
_FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "cases"

_PLACEHOLDER_PATTERN = re.compile(r"\{\{[^}]+\}\}")


def _load_fixture(name: str) -> dict[str, object]:
    return json.loads((_FIXTURES_DIR / name).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Core determinism + structural invariants
# ---------------------------------------------------------------------------


@pytest.fixture
def buried_template() -> TemplateDefinition:
    return parse_template_file(_STARTER_DIR / "buried_constraint_starter_v1.yaml")


def test_same_inputs_produce_byte_identical_cases(buried_template: TemplateDefinition) -> None:
    a = generate_case(buried_template, seed=42, difficulty=DifficultyLevel.MEDIUM)
    b = generate_case(buried_template, seed=42, difficulty=DifficultyLevel.MEDIUM)
    assert a.model_dump_json() == b.model_dump_json()


def test_different_seed_produces_different_case(buried_template: TemplateDefinition) -> None:
    a = generate_case(buried_template, seed=1, difficulty=DifficultyLevel.MEDIUM)
    b = generate_case(buried_template, seed=999, difficulty=DifficultyLevel.MEDIUM)
    assert a.model_dump() != b.model_dump()


def test_case_id_reflects_inputs(buried_template: TemplateDefinition) -> None:
    case = generate_case(buried_template, seed=42, difficulty=DifficultyLevel.HARD)
    assert "buried_constraint_starter_v1" in case.case_id
    assert "s42" in case.case_id
    assert "dhard" in case.case_id


def test_no_placeholders_survive_in_output(buried_template: TemplateDefinition) -> None:
    case = generate_case(buried_template, seed=42, difficulty=DifficultyLevel.MEDIUM)
    serialized = case.model_dump_json()
    assert not _PLACEHOLDER_PATTERN.search(serialized), (
        "unresolved {{placeholder}} in generated case"
    )


def test_turn_ids_are_contiguous_from_zero(buried_template: TemplateDefinition) -> None:
    case = generate_case(buried_template, seed=42, difficulty=DifficultyLevel.MEDIUM)
    ids = [t.id for t in case.transcript.turns]
    assert ids == list(range(len(ids)))


def test_distractor_count_matches_policy_per_difficulty(
    buried_template: TemplateDefinition,
) -> None:
    easy = generate_case(buried_template, seed=42, difficulty=DifficultyLevel.EASY)
    hard = generate_case(buried_template, seed=42, difficulty=DifficultyLevel.HARD)
    # Starter template config: easy=2, medium=4, hard=6.
    easy_distractors = sum("distractor" in t.tags for t in easy.transcript.turns)
    hard_distractors = sum("distractor" in t.tags for t in hard.transcript.turns)
    assert easy_distractors == 2
    assert hard_distractors == 6


def test_unconfigured_difficulty_raises(buried_template: TemplateDefinition) -> None:
    # Starter templates don't configure elite; the engine should reject.
    with pytest.raises(GenerationError, match="elite"):
        generate_case(buried_template, seed=42, difficulty=DifficultyLevel.ELITE)


def test_generated_transcript_only_contains_text_roles(
    buried_template: TemplateDefinition,
) -> None:
    case = generate_case(buried_template, seed=42, difficulty=DifficultyLevel.EASY)
    for t in case.transcript.turns:
        assert t.role in {TurnRole.USER, TurnRole.ASSISTANT, TurnRole.SYSTEM}


def test_ground_truth_has_resolved_values(buried_template: TemplateDefinition) -> None:
    case = generate_case(buried_template, seed=42, difficulty=DifficultyLevel.MEDIUM)
    # Starter template forbids "{{forbidden_action}}" — resolved to a real phrase.
    assert len(case.ground_truth.forbidden_behaviors) == 1
    forbidden = case.ground_truth.forbidden_behaviors[0]
    assert forbidden
    assert not _PLACEHOLDER_PATTERN.search(forbidden)


def test_deferred_items_plumbed_from_template_to_ground_truth(
    buried_template: TemplateDefinition,
) -> None:
    """Regression: ``deferred_items`` exists in the template schema but used
    to get dropped before being written into ``GroundTruth``.

    We mutate a real starter template's ground_truth section to populate the
    bucket and confirm the value round-trips through generation.
    """
    patched_gt = buried_template.ground_truth.model_copy(
        update={"deferred_items": ["hiring decision held for Q2"]}
    )
    patched_template = buried_template.model_copy(update={"ground_truth": patched_gt})

    case = generate_case(patched_template, seed=42, difficulty=DifficultyLevel.MEDIUM)
    assert case.ground_truth.deferred_items == ["hiring decision held for Q2"]


def test_evaluation_items_have_resolved_expected_values(
    buried_template: TemplateDefinition,
) -> None:
    case = generate_case(buried_template, seed=42, difficulty=DifficultyLevel.MEDIUM)
    for item in case.evaluation_items:
        assert not _PLACEHOLDER_PATTERN.search(item.prompt)
        for v in item.expected.values():
            if isinstance(v, str):
                assert not _PLACEHOLDER_PATTERN.search(v)


# ---------------------------------------------------------------------------
# Full suite generates successfully at every configured difficulty
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "difficulty", [DifficultyLevel.EASY, DifficultyLevel.MEDIUM, DifficultyLevel.HARD]
)
def test_all_starter_templates_generate(difficulty: DifficultyLevel) -> None:
    for template in load_suite(_STARTER_DIR):
        case = generate_case(template, seed=7, difficulty=difficulty)
        assert case.case_id
        assert case.transcript.turns  # at least one turn
        assert case.evaluation_items  # at least one item


# ---------------------------------------------------------------------------
# Regression fixtures — byte-identical output against committed expected
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("template_file", "fixture_name"),
    [
        (
            "buried_constraint_starter_v1.yaml",
            "buried_constraint_starter_v1_seed42_medium.json",
        ),
        (
            "decision_override_starter_v1.yaml",
            "decision_override_starter_v1_seed42_medium.json",
        ),
        (
            "entity_confusion_starter_v1.yaml",
            "entity_confusion_starter_v1_seed42_medium.json",
        ),
        (
            "reference_resolution_starter_v1.yaml",
            "reference_resolution_starter_v1_seed42_medium.json",
        ),
    ],
)
def test_starter_cases_match_committed_fixtures(template_file: str, fixture_name: str) -> None:
    template = parse_template_file(_STARTER_DIR / template_file)
    case = generate_case(template, seed=42, difficulty=DifficultyLevel.MEDIUM)
    expected = _load_fixture(fixture_name)
    actual = json.loads(case.model_dump_json())
    assert actual == expected
