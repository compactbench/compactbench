"""Entity confusion: look-alike people, ownership that changes hands, outside contractors.

What it tests:

- Does the artifact keep *which* Dana owns what, when two people share a first
  name and near-identical surnames?
- Does it follow ownership handovers — often between the look-alikes — across
  compactions? The previous owner is offered and counted as stale.
- Does it keep roles and companies attached to the right person?
- Does it keep who reported what?
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar

from compactbench.contracts import Probe, ProbeCategory, ValueKind
from compactbench.scenarios import probes
from compactbench.scenarios.builder import BuildContext
from compactbench.scenarios.families.base import Family, others, register_family, say, spread
from compactbench.scenarios.rng import Rng
from compactbench.scenarios.world import Person

_ROSTER = (
    "So nobody gets mixed up later — {people}.",
    "People you'll hear about on {project}: {people}.",
)
_ROSTER_RESTATE = ("Thanks, that helps keep everyone straight.",)
_MEMBER = ("{name} is our {role}",)
_MEMBER_EXTERNAL = ("{name} is the {role} on loan from {org}",)
_OWNS = (
    "{name} owns {project}'s {component}.",
    "Anything about the {component}, go to {name} — it's theirs.",
    "The {component} is {name}'s; route questions there.",
)
_OWNS_RESTATE = ("Got it — {component}: {name}.",)
_HANDOVER = (
    "Ownership change on {project}: the {component} moves from {old} to {name}, effective now.",
    "{name} has taken over the {component} from {old}.",
)
_HANDOVER_RESTATE = ("Updated — {component}: {name}.",)
_FLAGGED = ("{name} flagged {event}.",)
_FLAGGED_RESTATE = ("Thanks — I'll note that {name} raised it.",)
_INCIDENTS = (
    "the memory leak in the {component}",
    "the duplicate rows coming out of the {component}",
    "the expired certificate on staging",
    "the timeout spike on the {component}",
    "the race condition in the {component}'s retry path",
    "the broken pagination in the {component}",
    "the missing audit entries from the {component}",
)


@dataclass
class _Ownership:
    component: str
    owners: list[tuple[int, float, Person]] = field(default_factory=list[tuple[int, float, Person]])
    """``(cycle, position, owner)`` in the order they took over."""

    def owner_at(self, cycle: int) -> Person | None:
        held = [o for c, _, o in self.owners if c <= cycle]
        return held[-1] if held else None

    def previous_at(self, cycle: int) -> list[Person]:
        current = self.owner_at(cycle)
        return [o for c, _, o in self.owners if c <= cycle and o != current]


class EntityConfusion(Family):
    key: ClassVar[str] = "entity_confusion"
    version: ClassVar[str] = "2.0.0"
    title: ClassVar[str] = "Entity confusion"
    description: ClassVar[str] = (
        "Look-alike people, ownership handed back and forth between them across "
        "cycles, and roles and companies that must stay with the right person."
    )
    min_lookalikes: ClassVar[int] = 1

    def build(self, ctx: BuildContext) -> None:
        rng = ctx.rng
        profile = ctx.profile
        setting = ctx.setting
        project = ctx.project
        cast = list(setting.cast)
        lookalike_people = [p for pair in setting.lookalikes for p in pair]

        # --- cycle 0: introductions (roles, outside companies) ------------------
        intro_people = rng.shuffled(cast)
        groups = [intro_people[i : i + 3] for i in range(0, len(intro_people), 3)]
        intro_positions = spread(rng.child("intro-pos"), len(groups), 0.02, 0.4)
        for index, (group, pos) in enumerate(zip(groups, intro_positions, strict=True)):
            r = rng.child(f"intro:{index}")
            parts = [
                say(
                    ctx,
                    r,
                    "entity.member_external",
                    _MEMBER_EXTERNAL,
                    name=p.name,
                    role=p.role,
                    org=p.org,
                )
                if p.org is not None
                else say(ctx, r, "entity.member", _MEMBER, name=p.name, role=p.role)
                for p in group
            ]
            sentence = say(
                ctx, r, "entity.roster", _ROSTER, project=project, people="; ".join(parts)
            )
            ctx.state(
                r,
                0,
                pos,
                sentence,
                restatement=say(ctx, r, "entity.roster_restate", _ROSTER_RESTATE),
            )

        # --- ownership ------------------------------------------------------------
        components = rng.sample(setting.components, min(profile.items, len(setting.components)))
        ownerships = [_Ownership(c) for c in components]
        owner_pool = lookalike_people + [p for p in cast if p not in lookalike_people]
        own_positions = spread(rng.child("own-pos"), len(ownerships), 0.42, 0.85)
        for index, (own, pos) in enumerate(zip(ownerships, own_positions, strict=True)):
            owner = (
                owner_pool[index % len(owner_pool)]
                if index < len(lookalike_people)
                else rng.choice(cast)
            )
            own.owners.append((0, pos, owner))
            r = rng.child(f"own:{own.component}")
            fields: dict[str, object] = {
                "project": project,
                "component": own.component,
                "name": owner.name,
            }
            ctx.state(
                r,
                0,
                pos,
                say(ctx, r, "entity.owns", _OWNS, **fields),
                restatement=say(ctx, r, "entity.owns_restate", _OWNS_RESTATE, **fields),
            )

        # --- handovers: late in cycle 0 (hard and up) and in later cycles -------------
        def handover(r: Rng, cycle: int, position: float) -> None:
            own = r.choice(ownerships)
            current = own.owner_at(cycle)
            if current is None:
                return
            twin = next(
                (b if a == current else a for a, b in setting.lookalikes if current in (a, b)), None
            )
            new = (
                twin
                if twin is not None and r.chance(0.7)
                else r.choice([p for p in cast if p != current])
            )
            own.owners.append((cycle, position, new))
            fields = {
                "project": project,
                "component": own.component,
                "old": current.name,
                "name": new.name,
            }
            ctx.state(
                r,
                cycle,
                position,
                say(ctx, r, "entity.handover", _HANDOVER, **fields),
                restatement=say(ctx, r, "entity.handover_restate", _HANDOVER_RESTATE, **fields),
            )

        if profile.items >= 6:
            handover(rng.child("handover:0"), 0, rng.uniform(0.88, 0.98))
        for cycle in range(1, ctx.drift_cycles + 1):
            r = rng.child(f"handover-cycle:{cycle}")
            if not r.chance(profile.change_rate):
                continue
            # Ascending positions keep the transcript in the order the history was built.
            moves = 2 if profile.items >= 8 else 1
            for move, pos in enumerate(spread(r.child("pos"), moves, 0.1, 0.9)):
                handover(r.child(f"move:{move}"), cycle, pos)

        # --- who flagged what -----------------------------------------------------------
        incidents: list[tuple[int, str, Person]] = []
        for index in range(max(1, profile.items // 3)):
            r = rng.child(f"incident:{index}")
            cycle = 0 if index == 0 or ctx.drift_cycles == 0 else r.randint(0, ctx.drift_cycles)
            event = say(ctx, r, "entity.incident", _INCIDENTS, component=r.choice(components))
            if any(e == event for _, e, _ in incidents):
                continue
            reporter = r.choice(lookalike_people or cast)
            incidents.append((cycle, event, reporter))
            ctx.state(
                r,
                cycle,
                r.uniform(0.2, 0.95),
                say(ctx, r, "entity.flagged", _FLAGGED, name=reporter.name, event=event),
                restatement=say(
                    ctx, r, "entity.flagged_restate", _FLAGGED_RESTATE, name=reporter.name
                ),
            )

        # --- probes ---------------------------------------------------------------------
        for own in ownerships:

            def owner_probe(cycle: int, own: _Ownership = own) -> Probe | None:
                current = own.owner_at(cycle)
                if current is None:
                    return None
                return probes.single(
                    rng,
                    key=f"owner_{own.component.replace(' ', '_')}",
                    category=ProbeCategory.ENTITY_ATTRIBUTION,
                    question=f"Who currently owns {project}'s {own.component}?",
                    correct=current.name,
                    stale=[p.name for p in own.previous_at(cycle)],
                    distractors=[p.name for p in others(setting, current)],
                    origin_cycle=0,
                    options=profile.options,
                )

            ctx.ask_from(0, owner_probe)

        for person in lookalike_people:
            roles = [
                person.role,
                *(p.role for p in others(setting, person)),
                *setting.lexicon.roles,
            ]
            ctx.ask_from(
                0,
                lambda c, person=person, roles=roles: probes.single(
                    rng,
                    key=f"role_{person.first}_{person.last}",
                    category=ProbeCategory.ENTITY_ATTRIBUTION,
                    question=f"What is {person.name}'s role?",
                    correct=person.role,
                    distractors=roles[1:],
                    origin_cycle=0,
                    options=profile.options,
                ),
            )

        for person in [p for p in cast if p.org is not None]:
            orgs = [setting.company, *setting.lexicon.orgs]
            ctx.ask_from(
                0,
                lambda c, person=person, orgs=orgs: probes.single(
                    rng,
                    key=f"org_{person.first}_{person.last}",
                    category=ProbeCategory.ENTITY_ATTRIBUTION,
                    question=f"Which company is {person.name} from?",
                    correct=person.org or "",
                    distractors=orgs,
                    origin_cycle=0,
                    options=profile.options,
                ),
            )

        for index, (origin, event, reporter) in enumerate(incidents):
            ctx.ask_from(
                origin,
                lambda c, event=event, reporter=reporter, index=index, origin=origin: probes.single(
                    rng,
                    key=f"reporter_{index}",
                    category=ProbeCategory.ENTITY_ATTRIBUTION,
                    question=f"Who flagged {event}?",
                    correct=reporter.name,
                    distractors=[p.name for p in others(setting, reporter)],
                    origin_cycle=origin,
                    options=profile.options,
                ),
            )

        if profile.items >= 6:
            for person in lookalike_people[:2]:

                def portfolio(cycle: int, person: Person = person) -> Probe | None:
                    held = [o.component for o in ownerships if o.owner_at(cycle) == person]
                    if not held:
                        return None
                    lost = [
                        o.component
                        for o in ownerships
                        if person in o.previous_at(cycle) and o.component not in held
                    ]
                    return probes.values(
                        key=f"portfolio_{person.first}_{person.last}",
                        category=ProbeCategory.ENTITY_ATTRIBUTION,
                        question=f"List every {project} component {person.name} currently owns.",
                        answers=held,
                        kind=ValueKind.TEXT,
                        stale=lost,
                        origin_cycle=0,
                    )

                ctx.ask_from(0, portfolio)


register_family(EntityConfusion())
