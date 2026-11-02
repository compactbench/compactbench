"""Seeded randomness for case generation.

Every random choice a scenario makes goes through an :class:`Rng`. Child
streams are derived by label with SHA-256, so adding a new draw in one part
of a family never shifts the draws in another — and the same
``(family, seed, difficulty)`` produces the same case on any platform.
"""

from __future__ import annotations

import hashlib
import random
from collections.abc import Sequence
from typing import TypeVar

T = TypeVar("T")


def derive_seed(seed: int, label: str) -> int:
    """Derive a stable 64-bit sub-seed from ``seed`` and a text ``label``."""
    digest = hashlib.sha256(f"{seed}:{label}".encode()).digest()
    return int.from_bytes(digest[:8], "big", signed=False)


def derive_case_seed(namespace: str, seed_group: str, slot: int) -> int:
    """Seed for case ``slot`` of ``seed_group`` within ``namespace`` (suite + family + version)."""
    digest = hashlib.sha256(f"{namespace}:{seed_group}:{slot}".encode()).digest()
    return int.from_bytes(digest[:8], "big", signed=False)


class Rng:
    """A labelled, forkable wrapper around :class:`random.Random`."""

    def __init__(self, seed: int) -> None:
        self.seed = seed
        self._random = random.Random(seed)

    def child(self, label: str) -> Rng:
        """An independent stream for ``label``; unaffected by draws on this one."""
        return Rng(derive_seed(self.seed, label))

    def random(self) -> float:
        return self._random.random()

    def chance(self, p: float) -> bool:
        return self._random.random() < p

    def randint(self, low: int, high: int) -> int:
        return self._random.randint(low, high)

    def uniform(self, low: float, high: float) -> float:
        return self._random.uniform(low, high)

    def choice(self, items: Sequence[T]) -> T:
        if not items:
            raise ValueError("choice from an empty sequence")
        return items[self._random.randrange(len(items))]

    def sample(self, items: Sequence[T], k: int) -> list[T]:
        if k > len(items):
            raise ValueError(f"cannot sample {k} items from {len(items)}")
        return self._random.sample(list(items), k)

    def shuffled(self, items: Sequence[T]) -> list[T]:
        out = list(items)
        self._random.shuffle(out)
        return out
