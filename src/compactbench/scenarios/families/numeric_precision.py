"""Numeric precision: exact values that summaries round, drop, or attach to the wrong project.

What it tests:

- Does the artifact keep exact values — contract amounts, limits, dates,
  versions, identifiers — rather than "about $50k" or "early next year"?
- Does it keep each value attached to *this* project? Decoys state the same
  kind of value for a sibling project, often close in size.
- Does it keep the correction rather than the first figure? Early estimates
  are replaced by final numbers, and later cycles correct values again.
- Does it avoid inventing a value that was only ever given for another project?
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import ClassVar

from compactbench.contracts import NOT_STATED, Probe, ProbeCategory, ValueKind
from compactbench.scenarios import probes
from compactbench.scenarios.builder import BuildContext
from compactbench.scenarios.families.base import Family, human_value, register_family, say, spread
from compactbench.scenarios.lexicon import FactTemplate
from compactbench.scenarios.rng import Rng

_EPOCH = date(2026, 1, 1)
_ESTIMATE = (
    "Rough number for now: {project}'s {label} looks like {value}, but finance will confirm.",
    "Early estimate on {project}'s {label}: around {value}. Don't treat that as final.",
)
_FINAL = (
    "Final number is in — {project}'s {label} is {value}, not the estimate.",
    "Confirmed: {project}'s {label} is {value}. Ignore the earlier estimate.",
)
_CORRECTION = (
    "Correction on {project}'s {label}: it's {value}, not {old}.",
    "Small fix — {project}'s {label} changed to {value} (it was {old}).",
)
_SIBLING = (
    "For comparison — {statement} That's {other}, a different project.",
    "Don't mix these up: {statement} (That's {other}, not us.)",
)
_RESTATE = ("Noted: {label} {value}.",)


def draw_value(rng: Rng, fact: FactTemplate) -> str:
    """A canonical value for ``fact``."""
    if fact.choices:
        return rng.choice(fact.choices)
    if fact.kind == "money":
        return f"${rng.randint(fact.low // 50, fact.high // 50) * 50:,}"
    if fact.kind == "date":
        return (_EPOCH + timedelta(days=rng.randint(fact.low, fact.high))).isoformat()
    if fact.kind == "ident":
        return f"{fact.prefix}{rng.randint(fact.low, fact.high)}"
    return str(rng.randint(fact.low, fact.high))


def draw_near(rng: Rng, fact: FactTemplate, value: str, avoid: set[str]) -> str:
    """A different value of the same kind, close to ``value`` where that makes sense."""
    for _ in range(50):
        if fact.choices:
            candidate = rng.choice(fact.choices)
        elif fact.kind == "money":
            base = int(value.replace("$", "").replace(",", ""))
            delta = rng.choice((-1, 1)) * rng.randint(1, max(2, base // 1000)) * 50
            candidate = f"${max(base + delta, 50):,}"
        elif fact.kind == "number":
            base = int(value)
            candidate = str(max(1, base + rng.choice((-1, 1)) * rng.randint(1, max(2, base // 10))))
        elif fact.kind == "date":
            shifted = date.fromisoformat(value) + timedelta(
                days=rng.choice((-1, 1)) * rng.randint(1, 21)
            )
            candidate = shifted.isoformat()
        else:
            candidate = draw_value(rng, fact)
        if candidate != value and candidate not in avoid:
            return candidate
    return draw_value(rng, fact)


@dataclass
class _Fact:
    template: FactTemplate
    values: dict[int, str] = field(default_factory=dict[int, str])
    estimate: str | None = None
    sibling: tuple[str, str] | None = None
    """``(other project, value)`` stated as a decoy."""
    stated: bool = True
    """False for a fact only ever given for a sibling project."""

    def value_at(self, cycle: int) -> str | None:
        current: str | None = None
        for start in sorted(self.values):
            if start <= cycle:
                current = self.values[start]
        return current

    def before(self, cycle: int) -> list[str]:
        current = self.value_at(cycle)
        earlier = [v for c, v in sorted(self.values.items()) if c <= cycle and v != current]
        if self.estimate and self.estimate != current:
            earlier.insert(0, self.estimate)
        return earlier


class NumericPrecision(Family):
    key: ClassVar[str] = "numeric_precision"
    version: ClassVar[str] = "1.0.0"
    title: ClassVar[str] = "Numeric precision"
    description: ClassVar[str] = (
        "Exact amounts, limits, dates, versions and identifiers — estimated then "
        "finalized, corrected across cycles, and shadowed by look-alike values for "
        "sibling projects."
    )

    def build(self, ctx: BuildContext) -> None:
        rng = ctx.rng
        profile = ctx.profile
        project = ctx.project
        pool = rng.shuffled(ctx.setting.lexicon.facts)
        count = min(profile.items + 1, len(pool))
        facts = [_Fact(t) for t in pool[:count]]

        for fact in facts:
            r = rng.child(f"fact:{fact.template.key}")
            final = draw_value(r, fact.template)
            fact.values[0] = final
            if r.chance(profile.decoy_rate * 0.5) and fact.template.kind in (
                "money",
                "number",
                "date",
            ):
                fact.estimate = draw_near(r, fact.template, final, {final})
            if r.chance(profile.decoy_rate):
                other = r.choice(ctx.setting.other_projects)
                fact.sibling = (other, draw_near(r, fact.template, final, {final}))

        # One fact is only ever stated for a sibling project: asking it for this
        # project has no answer, and the sibling's value is the trap.
        if len(facts) >= 4:
            orphan = facts[-1]
            orphan.stated = False
            if orphan.sibling is None:
                other = rng.choice(ctx.setting.other_projects)
                orphan.sibling = (other, draw_value(rng.child("orphan"), orphan.template))

        for fact, pos in zip(facts, spread(rng.child("pos"), len(facts)), strict=True):
            self._place(ctx, rng.child(f"beats:{fact.template.key}"), fact, pos)

        for cycle in range(1, ctx.drift_cycles + 1):
            r = rng.child(f"correct:{cycle}")
            if not r.chance(profile.change_rate):
                continue
            live = [f for f in facts if f.stated]
            for fact in r.sample(live, min(2 if profile.items >= 8 else 1, len(live))):
                old = fact.value_at(cycle - 1) or ""
                new = draw_near(r, fact.template, old, set(fact.values.values()))
                fact.values[cycle] = new
                kind = fact.template.kind
                fields = {
                    "project": project,
                    "label": fact.template.label,
                    "value": human_value(new, kind, r, profile.indirect_rate),
                    "old": human_value(old, kind, r, profile.indirect_rate),
                }
                ctx.state(
                    r,
                    cycle,
                    r.uniform(0.1, 0.9),
                    say(ctx, r, "numeric.correction", _CORRECTION, **fields),
                    restatement=say(ctx, r, "numeric.restate", _RESTATE, **fields),
                )

        for fact in facts:
            ctx.ask_from(0, lambda c, fact=fact: self._probe(ctx, fact, c))

    def _place(self, ctx: BuildContext, rng: Rng, fact: _Fact, position: float) -> None:
        t = fact.template
        indirect = ctx.profile.indirect_rate
        if fact.sibling is not None:
            other, value = fact.sibling
            ctx.state(
                rng,
                0,
                rng.uniform(0.02, 0.98),
                say(
                    ctx,
                    rng,
                    "numeric.sibling",
                    _SIBLING,
                    other=other,
                    statement=rng.choice(t.statements).format(
                        project=other, value=human_value(value, t.kind, rng, indirect)
                    ),
                ),
            )
        if not fact.stated:
            return
        final = fact.values[0]
        if fact.estimate is not None:
            ctx.state(
                rng,
                0,
                max(position - 0.03, 0.0),
                say(
                    ctx,
                    rng,
                    "numeric.estimate",
                    _ESTIMATE,
                    project=ctx.project,
                    label=t.label,
                    value=human_value(fact.estimate, t.kind, rng, indirect),
                ),
            )
            sentence = say(
                ctx,
                rng,
                "numeric.final",
                _FINAL,
                project=ctx.project,
                label=t.label,
                value=human_value(final, t.kind, rng, indirect),
            )
            ctx.state(rng, 0, min(position + 0.03, 1.0), sentence)
            return
        sentence = rng.choice(t.statements).format(
            project=ctx.project, value=human_value(final, t.kind, rng, indirect)
        )
        ctx.state(
            rng,
            0,
            position,
            sentence,
            restatement=say(ctx, rng, "numeric.restate", _RESTATE, label=t.label, value=final),
        )

    def _probe(self, ctx: BuildContext, fact: _Fact, cycle: int) -> Probe:
        t = fact.template
        traps = [fact.sibling[1]] if fact.sibling is not None else []
        if not fact.stated:
            return probes.value(
                key=f"fact_{t.key}",
                category=ProbeCategory.ABSTENTION,
                question=t.question.replace("{project}", ctx.project),
                answer=NOT_STATED,
                kind=ValueKind(t.kind),
                traps=traps,
                origin_cycle=0,
            )
        return probes.value(
            key=f"fact_{t.key}",
            category=ProbeCategory.FACT_RECALL,
            question=t.question.replace("{project}", ctx.project),
            answer=fact.value_at(cycle) or NOT_STATED,
            kind=ValueKind(t.kind),
            stale=fact.before(cycle),
            traps=traps,
            origin_cycle=0,
        )


register_family(NumericPrecision())
