"""Family ABC, registry, and helpers shared by family implementations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from datetime import date
from typing import ClassVar

from compactbench.scenarios.builder import BuildContext
from compactbench.scenarios.rng import Rng
from compactbench.scenarios.world import Person, Setting


class Family(ABC):
    """A kind of compaction failure, expressed as a case generator.

    ``build`` places beats in the conversation and registers the probes to ask
    after each compaction. It must draw all randomness from ``ctx.rng`` (or
    children of it) so cases are reproducible.
    """

    key: ClassVar[str]
    version: ClassVar[str]
    title: ClassVar[str]
    description: ClassVar[str]
    min_lookalikes: ClassVar[int] = 0
    """Look-alike pairs the cast needs regardless of difficulty."""
    pools: ClassVar[tuple[str, ...]] = ()
    """Lexicon fields whose items this family turns into facts (``"topics"``…).

    In a mixed case, families that share a pool get disjoint shares of it, so
    two families never give the same topic two different answers.
    """

    @abstractmethod
    def build(self, ctx: BuildContext) -> None:
        """Populate ``ctx`` with beats and probes."""


class UnknownFamilyError(KeyError):
    """Requested family key is not registered."""


_REGISTRY: dict[str, Family] = {}


def register_family(family: Family) -> Family:
    """Register ``family`` under its key. Re-registering the same key replaces it."""
    _REGISTRY[family.key] = family
    return family


def get_family(key: str) -> Family:
    family = _REGISTRY.get(key)
    if family is None:
        raise UnknownFamilyError(f"unknown family {key!r}. Known: {sorted(_REGISTRY)}")
    return family


def list_families() -> list[str]:
    return sorted(_REGISTRY)


# --- helpers ---------------------------------------------------------------


def say(ctx: BuildContext, rng: Rng, key: str, defaults: Sequence[str], **fields: object) -> str:
    """Pick a sentence template for ``key`` and fill it.

    The setting's lexicon may replace the public ``defaults`` (see
    :attr:`Lexicon.phrases`). Templates use ``str.format`` fields.
    """
    templates = ctx.setting.lexicon.phrases.get(key) or tuple(defaults)
    return rng.choice(templates).format(**fields)


def lower_first(label: str) -> str:
    """``label`` for use mid-sentence: lowercase its first letter unless it starts an acronym."""
    first = label.split(" ", 1)[0]
    if len(first) > 1 and first.isupper():
        return label
    return label[:1].lower() + label[1:]


def spread(rng: Rng, count: int, low: float = 0.04, high: float = 0.96) -> list[float]:
    """``count`` sorted positions jittered evenly across ``[low, high]``."""
    if count <= 0:
        return []
    width = (high - low) / count
    return [low + width * (i + rng.uniform(0.1, 0.9)) for i in range(count)]


def others(setting: Setting, *exclude: Person) -> list[Person]:
    """Cast members other than ``exclude``, look-alikes of ``exclude`` first."""
    names = {p.name for p in exclude}
    firsts = {p.first for p in exclude}
    pool = [p for p in setting.cast if p.name not in names]
    return sorted(pool, key=lambda p: 0 if p.first in firsts else 1)


def human_date(iso: str, rng: Rng, chance: float) -> str:
    """Render an ISO date in a human format ``chance`` of the time."""
    if not rng.chance(chance):
        return iso
    parsed = date.fromisoformat(iso)
    month, short = parsed.strftime("%B"), parsed.strftime("%b")
    return rng.choice(
        (
            f"{month} {parsed.day}, {parsed.year}",
            f"{parsed.day} {month} {parsed.year}",
            f"{short} {parsed.day} {parsed.year}",
        )
    )


def human_money(amount: str, rng: Rng, chance: float) -> str:
    """Render ``$62,500`` as ``62.5k`` / ``$62.5K`` ``chance`` of the time."""
    if not rng.chance(chance):
        return amount
    number = float(amount.replace("$", "").replace(",", ""))
    if number >= 1000 and number % 100 == 0:
        short = f"{number / 1000:g}"
        return rng.choice((f"${short}k", f"{short}k dollars", f"${short}K"))
    return amount


def human_value(value: str, kind: str, rng: Rng, chance: float) -> str:
    if kind == "date":
        return human_date(value, rng, chance)
    if kind == "money":
        return human_money(value, rng, chance)
    if kind == "version" and rng.chance(chance):
        return value.removeprefix("v")
    return value
