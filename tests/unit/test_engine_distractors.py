"""Distractor-turn generation tests."""

from __future__ import annotations

import pytest

from compactbench.contracts import TurnRole
from compactbench.engine import generate_distractor_turns

pytestmark = pytest.mark.unit


def test_zero_count_returns_empty_list() -> None:
    assert generate_distractor_turns(0, 0, 1) == []


def test_negative_count_raises() -> None:
    with pytest.raises(ValueError, match=">= 0"):
        generate_distractor_turns(-1, 0, 1)


def test_turn_ids_are_sequential_from_start() -> None:
    turns = generate_distractor_turns(4, 10, seed=1)
    assert [t.id for t in turns] == [10, 11, 12, 13]


def test_roles_alternate_starting_with_user() -> None:
    turns = generate_distractor_turns(4, 0, seed=1)
    assert [t.role for t in turns] == [
        TurnRole.USER,
        TurnRole.ASSISTANT,
        TurnRole.USER,
        TurnRole.ASSISTANT,
    ]


def test_output_is_deterministic_for_same_seed() -> None:
    a = generate_distractor_turns(3, 0, seed=42)
    b = generate_distractor_turns(3, 0, seed=42)
    assert [t.content for t in a] == [t.content for t in b]


def test_output_varies_by_seed() -> None:
    a = generate_distractor_turns(3, 0, seed=1)
    b = generate_distractor_turns(3, 0, seed=999_999)
    # Probabilistic: extremely unlikely three draws all collide between two seeds.
    assert [t.content for t in a] != [t.content for t in b]


def test_all_turns_are_tagged_distractor() -> None:
    turns = generate_distractor_turns(3, 0, seed=1)
    for t in turns:
        assert "distractor" in t.tags
