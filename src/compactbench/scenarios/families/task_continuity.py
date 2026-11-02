"""Task continuity: a ticket board whose state keeps moving between compactions.

What it tests:

- Does the artifact keep which tickets are still open, by exact identifier?
- Does it follow status changes — started, blocked, done, reopened — rather
  than freezing the board as it was first described?
- Does it tell "basically done, just needs review" apart from done?
- Does it keep who each ticket is assigned to after reassignments, and what a
  blocked ticket is waiting on?
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

TODO, DOING, REVIEW, BLOCKED, DONE = "To do", "In progress", "In review", "Blocked", "Done"
_STATUSES = (TODO, DOING, REVIEW, BLOCKED, DONE)

_BOARD = (
    "Here's where the {project} board stands:\n{rows}",
    "Pasting the {project} tracker so we're on the same page:\n{rows}",
)
_ROW = ("{ticket} — {title} — {owner} — {status}",)
# Every update names the status it moves to, in the board's own words, so the
# answer key never rests on reading "can't move it forward" as Blocked.
_STARTED = (
    "{owner} started on {ticket}, so it's In progress now.",
    "{ticket} moves to In progress; {owner} picked it up.",
)
_REVIEW = (
    "{owner} says {ticket} is basically done, but it's In review, not merged yet.",
    "{ticket} is In review; {owner} still needs an approval before it counts as Done.",
)
_DONE = ("{ticket} is Done and merged.", "Closing {ticket}: {owner} shipped it, so it's Done.")
_BLOCKED = (
    "{ticket} is Blocked until {blocker} lands.",
    "{owner} can't move {ticket} forward. It's Blocked, waiting on {blocker}.",
)
_UNBLOCKED = ("{blocker} landed, so {ticket} is unblocked and back In progress.",)
_UNBLOCKED_DROPPED = (
    "{ticket} doesn't need {blocker} after all. It's unblocked and back In progress.",
    "We cut {ticket}'s dependency on {blocker}; it's back In progress with {owner}.",
)
_REOPENED = (
    "{ticket} regressed in staging, so we're reopening it. It's back In progress.",
    "We have to reopen {ticket}; the fix didn't hold. It's In progress again.",
)
_REASSIGNED = (
    "Reassigning {ticket} from {old} to {owner}.",
    "{owner} is taking over {ticket}; {old} is off it.",
)
_ACK = ("Board updated.", "Got it, updating my notes.")


@dataclass
class _Ticket:
    ident: str
    title: str
    history: list[tuple[int, str, Person, str | None]] = field(
        default_factory=list[tuple[int, str, Person, str | None]]
    )
    """``(cycle, status, owner, blocker)`` in order."""

    def at(self, cycle: int) -> tuple[str, Person, str | None]:
        latest = [h for h in self.history if h[0] <= cycle][-1]
        return latest[1], latest[2], latest[3]

    def statuses_before(self, cycle: int) -> list[str]:
        current = self.at(cycle)[0]
        return [s for c, s, _, _ in self.history if c <= cycle and s != current]


class TaskContinuity(Family):
    key: ClassVar[str] = "task_continuity"
    version: ClassVar[str] = "1.0.0"
    title: ClassVar[str] = "Task continuity"
    description: ClassVar[str] = (
        "A ticket board whose statuses, owners and blockers change across cycles, "
        "with work that is claimed done but is only in review."
    )

    def build(self, ctx: BuildContext) -> None:
        rng = ctx.rng
        profile = ctx.profile
        setting = ctx.setting
        lex = setting.lexicon
        cast = list(setting.cast)
        prefix = rng.choice(lex.ticket_prefixes)
        numbers = rng.sample(range(1000, 9999), profile.items + 3)
        components = rng.shuffled(setting.components)
        titles = rng.sample(lex.task_titles, min(len(numbers), len(lex.task_titles)))
        tickets = [
            _Ticket(
                f"{prefix}-{n}",
                title.replace("{component}", components[i % len(components)]),
            )
            for i, (n, title) in enumerate(zip(numbers, titles, strict=False))
        ]

        first_status = (TODO, DOING, DOING, REVIEW, DONE)
        for ticket in tickets:
            r = rng.child(f"init:{ticket.ident}")
            ticket.history.append((0, r.choice(first_status), r.choice(cast), None))
        self._board(ctx, rng.child("board"), tickets, position=rng.uniform(0.04, 0.2))

        positions = spread(rng.child("updates"), profile.items, 0.25, 0.95)
        for index, pos in enumerate(positions):
            self._update(ctx, rng.child(f"update0:{index}"), tickets, cycle=0, position=pos)
        for cycle in range(1, ctx.drift_cycles + 1):
            r = rng.child(f"cycle:{cycle}")
            moves = (3 if profile.items >= 8 else 2) if r.chance(profile.change_rate) else 1
            # Ascending positions keep the transcript in the order the history was built.
            for index, pos in enumerate(spread(r.child("pos"), moves, 0.05, 0.95)):
                self._update(ctx, r.child(f"update:{index}"), tickets, cycle=cycle, position=pos)

        project = ctx.project
        all_ids = [t.ident for t in tickets]

        def open_list(cycle: int) -> Probe:
            open_ids = [t.ident for t in tickets if t.at(cycle)[0] != DONE]
            closed_before = [
                t.ident
                for t in tickets
                if t.at(cycle)[0] == DONE
                and any(s != DONE for c, s, _, _ in t.history if c <= cycle)
            ]
            return probes.values(
                key="open_tickets",
                category=ProbeCategory.TASK_STATE,
                question=(
                    f"List every ticket on the {project} board that is not Done yet, by "
                    "ticket ID. Count only the tickets on that board."
                ),
                answers=open_ids,
                kind=ValueKind.IDENT,
                stale=closed_before,
                origin_cycle=0,
            )

        ctx.ask_from(0, open_list)

        for ticket in tickets[: profile.items]:

            def status(cycle: int, ticket: _Ticket = ticket) -> Probe:
                current, _, _ = ticket.at(cycle)
                return probes.single(
                    rng,
                    key=f"status_{ticket.ident}",
                    category=ProbeCategory.TASK_STATE,
                    question=f"What is the current status of {ticket.ident}?",
                    correct=current,
                    stale=ticket.statuses_before(cycle),
                    distractors=list(_STATUSES),
                    origin_cycle=0,
                    options=min(profile.options, len(_STATUSES) + 1),
                )

            def owner(cycle: int, ticket: _Ticket = ticket) -> Probe:
                _, person, _ = ticket.at(cycle)
                earlier = [p.name for c, _, p, _ in ticket.history if c <= cycle and p != person]
                return probes.single(
                    rng,
                    key=f"owner_{ticket.ident}",
                    category=ProbeCategory.ENTITY_ATTRIBUTION,
                    question=f"Who is {ticket.ident} assigned to now?",
                    correct=person.name,
                    stale=earlier[-1:],
                    distractors=[p.name for p in others(setting, person)],
                    origin_cycle=0,
                    options=profile.options,
                )

            def blocker(cycle: int, ticket: _Ticket = ticket) -> Probe | None:
                current, _, waiting_on = ticket.at(cycle)
                if current != BLOCKED or waiting_on is None:
                    return None
                return probes.single(
                    rng,
                    key=f"blocker_{ticket.ident}",
                    category=ProbeCategory.TASK_STATE,
                    question=f"Which ticket is {ticket.ident} waiting on?",
                    correct=waiting_on,
                    distractors=[i for i in all_ids if i != ticket.ident],
                    origin_cycle=cycle,
                    options=profile.options,
                )

            ctx.ask_from(0, status)
            if profile.items >= 4:
                ctx.ask_from(0, owner)
            ctx.ask_from(0, blocker)

    def _board(
        self, ctx: BuildContext, rng: Rng, tickets: list[_Ticket], *, position: float
    ) -> None:
        rows = "\n".join(
            say(
                ctx,
                rng,
                "task.row",
                _ROW,
                ticket=t.ident,
                title=t.title,
                owner=t.at(0)[1].name,
                status=t.at(0)[0],
            )
            for t in tickets
        )
        ctx.state(
            rng, 0, position, say(ctx, rng, "task.board", _BOARD, project=ctx.project, rows=rows)
        )

    def _update(
        self, ctx: BuildContext, rng: Rng, tickets: list[_Ticket], *, cycle: int, position: float
    ) -> None:
        ticket = rng.choice(tickets)
        status, owner, waiting_on = ticket.at(cycle)
        fields: dict[str, object] = {"ticket": ticket.ident, "owner": owner.name}
        if status != DONE and rng.chance(0.2):
            new_owner = rng.choice(others(ctx.setting, owner)[:3] or [owner])
            ticket.history.append((cycle, status, new_owner, waiting_on))
            fields.update(owner=new_owner.name, old=owner.name)
            key, defaults = "task.reassigned", _REASSIGNED
        elif status == TODO:
            ticket.history.append((cycle, DOING, owner, None))
            key, defaults = "task.started", _STARTED
        elif status == DOING and rng.chance(0.5):
            # Only tickets that are themselves moving can block, so dependencies never loop.
            candidates = [
                t for t in tickets if t is not ticket and t.at(cycle)[0] not in (DONE, BLOCKED)
            ]
            if not candidates:
                return
            blocking = rng.choice(candidates).ident
            ticket.history.append((cycle, BLOCKED, owner, blocking))
            fields["blocker"] = blocking
            key, defaults = "task.blocked", _BLOCKED
        elif status == DOING:
            ticket.history.append((cycle, REVIEW, owner, None))
            key, defaults = "task.review", _REVIEW
        elif status == REVIEW:
            ticket.history.append((cycle, DONE, owner, None))
            key, defaults = "task.done", _DONE
        elif status == BLOCKED:
            ticket.history.append((cycle, DOING, owner, None))
            fields["blocker"] = waiting_on or "the dependency"
            # "X landed" would claim the blocker is done, so say so only when it is.
            landed = any(t.ident == waiting_on and t.at(cycle)[0] == DONE for t in tickets)
            if landed:
                key, defaults = "task.unblocked", _UNBLOCKED
            else:
                key, defaults = "task.unblocked_dropped", _UNBLOCKED_DROPPED
        elif rng.chance(0.5):
            ticket.history.append((cycle, DOING, owner, None))
            key, defaults = "task.reopened", _REOPENED
        else:
            return
        ctx.state(
            rng,
            cycle,
            position,
            say(ctx, rng, key, defaults, **fields),
            restatement=say(ctx, rng, "task.ack", _ACK),
        )


register_family(TaskContinuity())
