"""The setting a case takes place in: the project, the company and the cast."""

from __future__ import annotations

from dataclasses import dataclass

from compactbench.scenarios.lexicon import Lexicon
from compactbench.scenarios.profile import Profile
from compactbench.scenarios.rng import Rng

_BASE_CAST = 5


@dataclass(frozen=True)
class Person:
    first: str
    last: str
    role: str
    org: str | None = None
    """Set for people from outside the company (contractors, vendors)."""

    @property
    def name(self) -> str:
        return f"{self.first} {self.last}"


@dataclass(frozen=True)
class Setting:
    lexicon: Lexicon
    project: str
    other_projects: tuple[str, ...]
    """Sibling projects, used for rules and decisions that apply elsewhere."""
    company: str
    user: Person
    """Who is talking to the assistant."""
    cast: tuple[Person, ...]
    """Everyone else who gets mentioned, look-alikes first."""
    lookalikes: tuple[tuple[Person, Person], ...]
    components: tuple[str, ...]


def build_setting(rng: Rng, lexicon: Lexicon, profile: Profile, *, extra_cast: int = 0) -> Setting:
    """Pick a project, a company and a cast for one case."""
    projects = rng.sample(lexicon.projects, 4)
    company = rng.choice(lexicon.orgs)
    outside_orgs = [o for o in lexicon.orgs if o != company]

    used_names: set[str] = set()
    people: list[Person] = []
    roles = rng.shuffled(lexicon.roles)

    def _role() -> str:
        return roles[len(people) % len(roles)]

    lookalike_pairs: list[tuple[Person, Person]] = []
    groups = rng.sample(
        lexicon.lookalike_last_names, min(profile.lookalikes, len(lexicon.lookalike_last_names))
    )
    for group in groups:
        first = rng.choice([f for f in lexicon.first_names if f not in {p.first for p in people}])
        last_a, last_b = rng.sample(group, 2)
        a = Person(first=first, last=last_a, role=_role())
        people.append(a)
        b = Person(
            first=first,
            last=last_b,
            role=_role(),
            org=rng.choice(outside_orgs) if rng.chance(0.4) else None,
        )
        people.append(b)
        lookalike_pairs.append((a, b))
        used_names.update({a.name, b.name})

    target = _BASE_CAST + profile.items + extra_cast
    taken_first = {p.first for p in people}
    while len(people) < target:
        first = rng.choice(lexicon.first_names)
        last = rng.choice(lexicon.last_names)
        if first in taken_first or f"{first} {last}" in used_names:
            continue
        person = Person(
            first=first,
            last=last,
            role=_role(),
            org=rng.choice(outside_orgs) if rng.chance(0.15) else None,
        )
        people.append(person)
        taken_first.add(first)
        used_names.add(person.name)

    user_first = rng.choice([f for f in lexicon.first_names if f not in taken_first])
    user = Person(first=user_first, last=rng.choice(lexicon.last_names), role="tech lead")
    return Setting(
        lexicon=lexicon,
        project=projects[0],
        other_projects=tuple(projects[1:]),
        company=company,
        user=user,
        cast=tuple(people),
        lookalikes=tuple(lookalike_pairs),
        components=tuple(rng.sample(lexicon.components, min(10, len(lexicon.components)))),
    )
