"""Difficulty profiles: how long, how dense and how adversarial a case is."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Difficulty(StrEnum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"
    ELITE = "elite"


@dataclass(frozen=True)
class Profile:
    """Knobs a family reads when it builds a case.

    Token targets are approximate (``cl100k_base``); filler is added until a
    segment reaches its target, so real sizes land within a few percent.
    """

    initial_tokens: int
    """Size of the opening conversation (cycle 0)."""
    cycle_tokens: int
    """Size of each later segment."""
    drift_cycles: int
    """Default number of compactions after the first."""
    items: int
    """How many tracked things (rules, topics, people…) a family introduces."""
    options: int
    """Answer options per choice question, including 'not stated'."""
    lookalikes: int
    """Pairs of easily confused people in the cast."""
    decoy_rate: float
    """Chance each real item gets a near-miss decoy (wrong scope, hypothetical, rejected)."""
    indirect_rate: float
    """Chance an item is stated indirectly rather than spelled out."""
    embed_rate: float
    """Chance an item is buried inside a long pasted document or tool output."""
    restate_rate: float
    """Chance the assistant cleanly restates an item right after it is introduced."""
    change_rate: float
    """Chance per later cycle that an earlier item is changed, revoked or handed over."""


PROFILES: dict[Difficulty, Profile] = {
    Difficulty.EASY: Profile(
        initial_tokens=1_500,
        cycle_tokens=600,
        drift_cycles=2,
        items=3,
        options=4,
        lookalikes=0,
        decoy_rate=0.3,
        indirect_rate=0.2,
        embed_rate=0.1,
        restate_rate=0.8,
        change_rate=0.5,
    ),
    Difficulty.MEDIUM: Profile(
        initial_tokens=6_000,
        cycle_tokens=2_000,
        drift_cycles=3,
        items=4,
        options=5,
        lookalikes=1,
        decoy_rate=0.6,
        indirect_rate=0.4,
        embed_rate=0.3,
        restate_rate=0.5,
        change_rate=0.7,
    ),
    Difficulty.HARD: Profile(
        initial_tokens=16_000,
        cycle_tokens=5_000,
        drift_cycles=4,
        items=6,
        options=6,
        lookalikes=2,
        decoy_rate=0.8,
        indirect_rate=0.6,
        embed_rate=0.5,
        restate_rate=0.3,
        change_rate=0.85,
    ),
    Difficulty.ELITE: Profile(
        initial_tokens=32_000,
        cycle_tokens=8_000,
        drift_cycles=4,
        items=8,
        options=7,
        lookalikes=3,
        decoy_rate=1.0,
        indirect_rate=0.75,
        embed_rate=0.6,
        restate_rate=0.15,
        change_rate=1.0,
    ),
}
