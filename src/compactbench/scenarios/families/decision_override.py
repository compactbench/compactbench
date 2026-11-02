"""Decision overrides: decisions that get changed, reverted, and carved up over time.

What it tests:

- Does the artifact keep the *current* decision, not the first one? Every
  superseded value is offered as an answer and counted as stale if picked.
- Does it survive reverts (A → B → A), where the stale answer is the middle one?
- Does it keep scoped exceptions ("Postgres everywhere except the export job")?
- Does it remember who made the latest call, among look-alike names?
- Does it keep exact values — dates, amounts, versions — through rewrites?
- Does it resist proposals that were floated and rejected?
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar

from compactbench.contracts import Probe, ProbeCategory, TurnRole, ValueKind
from compactbench.scenarios import probes
from compactbench.scenarios.builder import BuildContext
from compactbench.scenarios.families.base import (
    Family,
    human_value,
    others,
    register_family,
    say,
    spread,
)
from compactbench.scenarios.lexicon import DecisionTopic
from compactbench.scenarios.noise import TurnDraft
from compactbench.scenarios.rng import Rng
from compactbench.scenarios.world import Person

_INITIAL = (
    "Decision for {project}, {name}'s call: the {label} is {value}.",
    "{name} made the call on {project}'s {label} — {value} it is.",
    "After the comparison, {name} signed off on {value} as {project}'s {label}.",
)
_OVERRIDE = (
    "Change of plan on {project}'s {label}, per {name}: {old} is out, {value} replaces it.",
    "{name} overruled the earlier choice — {project}'s {label} moves from {old} to {value}.",
    "Heads up: the {label} for {project} is now {value} instead of {old} ({name} decided this morning).",
)
_REVERT = ("{name} is reverting {project}'s {label} back to {value} — {old} didn't work out.",)
_RESTATE = ("Noted — {project}'s {label}: {value}.",)
_EXCEPTION_KEPT = ("The {component} keeps its own setup.",)
_PROPOSAL = ("{name} floated switching {project}'s {label} to {value}.",)
_PROPOSAL_REPLY = ("Switching now would cost more than it saves, as far as I can tell.",)
_DECLINED = ("Agreed — we're not doing that. No change.",)
_EXCEPTION = (
    "One exception on the {label}: {project}'s {component} uses {value}, whatever the rest of {project} uses.",
)
_EXCEPTION_RESTATE = ("Understood — the {component} is on {value}.",)


@dataclass(frozen=True)
class _Change:
    cycle: int
    position: float
    value: str
    by: Person


@dataclass
class _Topic:
    topic: DecisionTopic
    changes: list[_Change] = field(default_factory=list[_Change])
    rejected: list[str] = field(default_factory=list[str])
    exception: tuple[str, str] | None = None
    """``(component, value)`` that keeps its own choice regardless of the general one."""

    def history(self, cycle: int) -> list[_Change]:
        return [c for c in self.changes if c.cycle <= cycle]

    def current(self, cycle: int) -> _Change | None:
        hist = self.history(cycle)
        return hist[-1] if hist else None


def _origin(t: _Topic) -> int:
    return t.changes[0].cycle


class DecisionOverride(Family):
    key: ClassVar[str] = "decision_override"
    pools: ClassVar[tuple[str, ...]] = ("topics",)
    version: ClassVar[str] = "2.0.0"
    title: ClassVar[str] = "Decision overrides"
    description: ClassVar[str] = (
        "Decisions changed, reverted and given scoped exceptions across cycles, "
        "with rejected proposals and look-alike deciders."
    )

    def build(self, ctx: BuildContext) -> None:
        rng = ctx.rng
        profile = ctx.profile
        lex = ctx.setting.lexicon
        cast = list(ctx.setting.cast)

        chosen = rng.sample(lex.topics, min(profile.items, len(lex.topics)))
        topics = [_Topic(t) for t in chosen]

        # --- cycle 0: an initial decision per topic, some overridden later in the segment
        firsts = spread(rng.child("first-pos"), len(topics), 0.03, 0.55)
        for topic, pos in zip(topics, firsts, strict=True):
            r = rng.child(f"topic:{topic.topic.key}")
            order = r.shuffled(topic.topic.options)
            topic.changes.append(_Change(0, pos, order[0], r.choice(cast)))
            if r.chance(0.35 + 0.4 * profile.change_rate):
                topic.changes.append(
                    _Change(0, r.uniform(pos + 0.1, 0.97), order[1], r.choice(cast))
                )
                if profile.items >= 6 and r.chance(0.35):
                    # Revert: back to the first choice, which makes the middle one stale.
                    topic.changes.append(
                        _Change(
                            0,
                            r.uniform(topic.changes[-1].position + 0.02, 0.99),
                            order[0],
                            r.choice(cast),
                        )
                    )
            if r.chance(profile.decoy_rate):
                topic.rejected.append(
                    next(o for o in order if o not in {c.value for c in topic.changes})
                )

        # --- later cycles: overrides arrive after the first compaction ----------
        for cycle in range(1, ctx.drift_cycles + 1):
            r = rng.child(f"cycle:{cycle}")
            if not r.chance(profile.change_rate):
                continue
            moves = 2 if profile.items >= 8 else 1
            for topic in r.sample(topics, min(moves, len(topics))):
                current = topic.changes[-1].value
                previous = {c.value for c in topic.changes}
                fresh = [o for o in topic.topic.options if o not in previous]
                value = (
                    r.choice(fresh)
                    if fresh and r.chance(0.7)
                    else r.choice([o for o in topic.topic.options if o != current])
                )
                topic.changes.append(_Change(cycle, r.uniform(0.1, 0.9), value, r.choice(cast)))

        # --- a scoped exception on a text topic (hard and up) ----------------------
        if profile.items >= 6:
            text_topics = [t for t in topics if t.topic.value_kind == "text"]
            if text_topics:
                topic = rng.choice(text_topics)
                component = rng.choice(ctx.setting.components)
                # Not a value the team chose or turned down: the carve-out has to read
                # as its own decision, not as a rejected proposal coming back.
                used = {c.value for c in topic.changes} | set(topic.rejected)
                candidates = [o for o in topic.topic.options if o not in used]
                if candidates:
                    topic.exception = (component, rng.choice(candidates))

        for topic in topics:
            self._place(ctx, rng.child(f"beats:{topic.topic.key}"), topic)

        # --- probes ------------------------------------------------------------------
        for topic in topics:
            self._ask(ctx, rng, topic)

    # -- beats ----------------------------------------------------------------------

    def _place(self, ctx: BuildContext, rng: Rng, topic: _Topic) -> None:
        project = ctx.project
        label = topic.topic.label
        kind = topic.topic.value_kind
        indirect = ctx.profile.indirect_rate
        for index, change in enumerate(topic.changes):
            r = rng.child(f"change:{index}")
            shown = human_value(change.value, kind, r, indirect)
            fields: dict[str, object] = {
                "project": project,
                "label": label,
                "value": shown,
                "name": change.by.name,
            }
            if index == 0:
                sentence = say(ctx, r, "decision.initial", _INITIAL, **fields)
            else:
                fields["old"] = human_value(topic.changes[index - 1].value, kind, r, indirect)
                reverting = change.value in {c.value for c in topic.changes[: index - 1]}
                key, defaults = (
                    ("decision.revert", _REVERT) if reverting else ("decision.override", _OVERRIDE)
                )
                sentence = say(ctx, r, key, defaults, **fields)
                if topic.exception is not None and change.cycle > 0:
                    sentence += " " + say(
                        ctx,
                        r,
                        "decision.exception_kept",
                        _EXCEPTION_KEPT,
                        component=topic.exception[0],
                    )
            ctx.state(
                r,
                change.cycle,
                change.position,
                sentence,
                restatement=say(ctx, r, "decision.restate", _RESTATE, **fields),
            )

        for index, value in enumerate(topic.rejected):
            r = rng.child(f"rejected:{index}")
            fields = {
                "project": project,
                "label": label,
                "value": human_value(value, kind, r, indirect),
                "name": r.choice(list(ctx.setting.cast)).name,
            }
            after = topic.changes[0].position
            ctx.place(
                0,
                r.uniform(after + 0.01, min(after + 0.3, 0.99)),
                [
                    TurnDraft(TurnRole.USER, say(ctx, r, "decision.proposal", _PROPOSAL, **fields)),
                    TurnDraft(
                        TurnRole.ASSISTANT,
                        say(ctx, r, "decision.proposal_reply", _PROPOSAL_REPLY, **fields),
                    ),
                    TurnDraft(
                        TurnRole.USER,
                        say(ctx, r, "decision.proposal_declined", _DECLINED, **fields),
                    ),
                ],
            )

        if topic.exception is not None:
            component, value = topic.exception
            r = rng.child("exception")
            cycle0 = [c for c in topic.changes if c.cycle == 0]
            fields = {"project": project, "label": label, "component": component, "value": value}
            ctx.state(
                r,
                0,
                min(cycle0[-1].position + r.uniform(0.01, 0.05), 0.995),
                say(ctx, r, "decision.exception", _EXCEPTION, **fields),
                restatement=say(ctx, r, "decision.exception_restate", _EXCEPTION_RESTATE, **fields),
            )

    # -- probes ---------------------------------------------------------------------

    def _ask(self, ctx: BuildContext, rng: Rng, topic: _Topic) -> None:
        project = ctx.project
        t = topic.topic
        options = ctx.profile.options

        def state(cycle: int) -> Probe | None:
            current = topic.current(cycle)
            if current is None:
                return None
            stale = [c.value for c in topic.history(cycle) if c.value != current.value]
            question = t.question.replace("{project}", project)
            if t.value_kind != "text":
                return probes.value(
                    key=f"decision_{t.key}",
                    category=ProbeCategory.DECISION_STATE,
                    question=question,
                    answer=current.value,
                    kind=ValueKind(t.value_kind),
                    stale=stale,
                    origin_cycle=_origin(topic),
                )
            if topic.exception is not None:
                question = question.rstrip("?") + " overall (apart from any exceptions)?"
            return probes.single(
                rng,
                key=f"decision_{t.key}",
                category=ProbeCategory.DECISION_STATE,
                question=question,
                correct=current.value,
                stale=stale,
                traps=topic.rejected,
                distractors=list(t.options),
                origin_cycle=_origin(topic),
                options=options,
            )

        ctx.ask_from(_origin(topic), state)

        if topic.exception is not None:
            component, value = topic.exception

            def scoped(cycle: int) -> Probe | None:
                current = topic.current(cycle)
                if current is None:
                    return None
                return probes.single(
                    rng,
                    key=f"exception_{t.key}",
                    category=ProbeCategory.DECISION_STATE,
                    question=f"Which {t.label} does {project}'s {component} use?",
                    correct=value,
                    distractors=[current.value, *t.options],
                    origin_cycle=0,
                    options=options,
                )

            ctx.ask_from(0, scoped)

        if ctx.profile.items >= 6:

            def previous(cycle: int) -> Probe | None:
                hist = topic.history(cycle)
                if len(hist) < 2:
                    return None
                before = hist[-2].value
                if t.value_kind != "text":
                    return probes.value(
                        key=f"previous_{t.key}",
                        category=ProbeCategory.DECISION_STATE,
                        question=(
                            f"What was {project}'s {t.label} immediately before the most recent change?"
                        ),
                        answer=before,
                        kind=ValueKind(t.value_kind),
                        origin_cycle=hist[-1].cycle,
                    )
                return probes.single(
                    rng,
                    key=f"previous_{t.key}",
                    category=ProbeCategory.DECISION_STATE,
                    question=f"What was {project}'s {t.label} immediately before the most recent change?",
                    correct=before,
                    distractors=[hist[-1].value, *topic.rejected, *t.options],
                    origin_cycle=hist[-1].cycle,
                    options=options,
                )

            ctx.ask_from(_origin(topic), previous)

        if ctx.profile.items >= 4 and rng.child(f"decider:{t.key}").chance(0.6):

            def decider(cycle: int) -> Probe | None:
                current = topic.current(cycle)
                if current is None:
                    return None
                earlier = [c.by.name for c in topic.history(cycle) if c.by.name != current.by.name]
                return probes.single(
                    rng,
                    key=f"decider_{t.key}",
                    category=ProbeCategory.ENTITY_ATTRIBUTION,
                    question=f"Who made the most recent call on {project}'s {t.label}?",
                    correct=current.by.name,
                    stale=earlier[-1:],
                    distractors=[p.name for p in others(ctx.setting, current.by)],
                    origin_cycle=current.cycle,
                    options=options,
                )

            ctx.ask_from(_origin(topic), decider)


register_family(DecisionOverride())
