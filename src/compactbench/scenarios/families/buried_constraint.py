"""Buried constraints: rules stated once, deep in the conversation, among look-alike rules.

What it tests:

- Do rules survive compaction when they are stated once, often indirectly,
  inside pasted notes or tool output?
- Does the artifact keep a rule's *scope*? Decoys are rules for a sibling
  project, hypotheticals, and proposals that were rejected.
- Does it track change? In later cycles rules are added, lifted, and have
  their limits changed.
- Can the reader *apply* the rules — spot which proposed next steps break one?
- Does the artifact invent a decision for a question that was only parked?
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar

from compactbench.contracts import NOT_STATED, Probe, ProbeCategory, TurnRole, ValueKind
from compactbench.scenarios import probes
from compactbench.scenarios.builder import BuildContext
from compactbench.scenarios.families.base import (
    Family,
    lower_first,
    register_family,
    say,
    spread,
)
from compactbench.scenarios.lexicon import RuleTemplate
from compactbench.scenarios.noise import TurnDraft
from compactbench.scenarios.rng import Rng

_GROUP = 4
_PARKED_ASK = ("Should {project} start {question}?",)
_PARKED_REPLY = ("There are arguments both ways. It might be worth getting the team's view first.",)
_PARKED = ("Yeah, let's park that one for now.",)
_RESTATE = ("Understood — {rule} for {project}.",)
_OTHER_SCOPE = (
    'For context, this is the {other} team\'s policy, not ours: "{statement}" '
    "It doesn't apply to {project}.",
)
_OTHER_SCOPE_REPLY = ("Okay — that's {other}-only.",)
_HYPOTHETICAL = (
    "If {project} ever ends up in scope for the payments audit we'd probably adopt "
    "\"{rule}\" as well — but we're not, so it doesn't apply today.",
)
_HYPOTHETICAL_REPLY = ("Good to know, nothing to change then.",)
_PROPOSAL = ('{name} proposed adding "{rule}" as a rule for {project}.',)
_PROPOSAL_REPLY = ("It would slow the team down for very little benefit at this stage.",)
_DECLINED = ("Agreed. We're not adopting it.",)
_LIFTED = (
    'Update for {project}: "{rule}" no longer applies — {reason}, so that rule is lifted as of today.',
)
_LIFTED_RESTATE = ("Okay, that rule is lifted for {project}.",)
_LIMIT_CHANGED = ("Heads up, the limit changed: {statement}",)
_LIMIT_RESTATE = ("Got it, new limit noted.",)
_LIFT_REASONS = (
    "the audit wrapped up",
    "the migration finished",
    "ops has weekend cover now",
    "legal signed off on the new setup",
    "the vendor fixed it on their side",
)


@dataclass
class _Rule:
    template: RuleTemplate
    introduced: int
    values: dict[int, str] = field(default_factory=dict[int, str])
    """Value in force from each cycle where it was set (valued rules only)."""
    lifted: int | None = None

    def active(self, cycle: int) -> bool:
        return self.introduced <= cycle and (self.lifted is None or self.lifted > cycle)

    def value_at(self, cycle: int) -> str | None:
        current: str | None = None
        for start in sorted(self.values):
            if start <= cycle:
                current = self.values[start]
        return current

    def values_before(self, cycle: int) -> list[str]:
        current = self.value_at(cycle)
        return [v for start, v in sorted(self.values.items()) if start <= cycle and v != current]


def _fill(text: str, project: str, value: str | None) -> str:
    return text.replace("{project}", project).replace("{n}", value or "")


def _shown(template: RuleTemplate, value: str, rng: Rng, chance: float) -> str:
    """How a rule's value is written in the conversation (money as ``6,500`` or ``6.5k``)."""
    if template.value_kind != "money":
        return value
    amount = int(value)
    return f"{amount / 1000:g}k" if rng.chance(chance) else f"{amount:,}"


class BuriedConstraint(Family):
    key: ClassVar[str] = "buried_constraint"
    version: ClassVar[str] = "2.0.0"
    title: ClassVar[str] = "Buried constraints"
    description: ClassVar[str] = (
        "Rules stated once and buried among look-alike rules for other projects, "
        "hypotheticals and rejected proposals; later cycles add, lift and change rules."
    )

    def build(self, ctx: BuildContext) -> None:
        rng = ctx.rng
        lex = ctx.setting.lexicon
        profile = ctx.profile
        project = ctx.project

        pool = rng.shuffled(lex.rules)
        count = min(profile.items, len(pool) // 2)
        real = [_Rule(t, introduced=0) for t in pool[:count]]
        spare = pool[count:]

        # --- cycle 0: state every rule once --------------------------------
        for rule, pos in zip(real, spread(rng.child("rule-pos"), len(real)), strict=True):
            r = rng.child(f"rule:{rule.template.key}")
            if rule.template.values:
                rule.values[0] = r.choice(rule.template.values)
            self._state_rule(ctx, r, rule, cycle=0, position=pos)

        # --- decoys --------------------------------------------------------
        decoys: list[RuleTemplate] = []
        for i in range(len(real)):
            r = rng.child(f"decoy:{i}")
            if not spare or not r.chance(profile.decoy_rate):
                continue
            decoy = spare.pop(0)
            decoys.append(decoy)
            self._place_decoy(ctx, r, decoy, position=r.uniform(0.05, 0.95))
        never_mentioned = spare[:2]
        spare = spare[2:]

        # --- later cycles: add, lift, change ---------------------------------
        for cycle in range(1, ctx.drift_cycles + 1):
            r = rng.child(f"change:{cycle}")
            if not r.chance(profile.change_rate):
                continue
            # Ascending positions keep the transcript in the order the history was built.
            moves = 2 if profile.items >= 8 else 1
            for move, pos in enumerate(spread(r.child("pos"), moves, 0.1, 0.9)):
                self._change(ctx, r.child(f"move:{move}"), real, spare, cycle, pos)

        # --- a parked question that never gets decided -------------------------
        question = rng.choice(lex.open_questions)
        pos = rng.uniform(0.2, 0.8)
        ctx.place(
            0,
            pos,
            [
                TurnDraft(
                    TurnRole.USER,
                    say(
                        ctx,
                        rng,
                        "constraint.parked_ask",
                        _PARKED_ASK,
                        project=project,
                        question=question,
                    ),
                ),
                TurnDraft(
                    TurnRole.ASSISTANT, say(ctx, rng, "constraint.parked_reply", _PARKED_REPLY)
                ),
                TurnDraft(TurnRole.USER, say(ctx, rng, "constraint.parked", _PARKED)),
            ],
        )

        # --- probes -------------------------------------------------------------
        groups = [real[i : i + _GROUP] for i in range(0, len(real), _GROUP)]
        decoy_groups = [decoys[i :: len(groups)] for i in range(len(groups))] if groups else []

        def recall(cycle: int, index: int) -> Probe | None:
            members = [m for m in groups[index] if m.introduced <= cycle]
            if not members:
                return None
            return probes.multi(
                rng,
                key=f"rules_in_force_{index}",
                category=ProbeCategory.CONSTRAINT_RECALL,
                question=(
                    f"Which of these rules currently apply to {project}? Select every one "
                    "that applies; ignore rules for other projects and ideas that were not adopted."
                ),
                correct=[m.template.label for m in members if m.active(cycle)],
                stale=[m.template.label for m in members if not m.active(cycle)],
                traps=[d.label for d in decoy_groups[index]],
                wrong=[t.label for t in never_mentioned],
                origin_cycle=min(m.introduced for m in members),
                max_options=profile.options + 1,
            )

        def apply(cycle: int, index: int) -> Probe | None:
            members = [m for m in groups[index] if m.introduced <= cycle]
            if not members:
                return None
            return probes.multi(
                rng,
                key=f"violations_{index}",
                category=ProbeCategory.CONSTRAINT_APPLICATION,
                question=(
                    f"The team is considering these next steps for {project}. Which of them "
                    f"would break a rule that currently applies to {project}? Select every one."
                ),
                correct=[m.template.violation for m in members if m.active(cycle)],
                stale=[m.template.violation for m in members if not m.active(cycle)],
                traps=[d.violation for d in decoy_groups[index]],
                wrong=[m.template.compliant for m in members],
                origin_cycle=min(m.introduced for m in members),
                max_options=profile.options + 1,
            )

        for index in range(len(groups)):
            ctx.ask_from(0, lambda c, i=index: recall(c, i))
            ctx.ask_from(0, lambda c, i=index: apply(c, i))

        for rule in real:
            if not rule.template.values:
                continue

            def limit(cycle: int, rule: _Rule = rule) -> Probe | None:
                current = rule.value_at(cycle)
                if current is None or not rule.active(cycle):
                    return None
                return probes.value(
                    key=f"limit_{rule.template.key}",
                    category=ProbeCategory.CONSTRAINT_RECALL,
                    question=_fill(rule.template.value_question, project, None),
                    answer=current,
                    kind=ValueKind(rule.template.value_kind),
                    stale=rule.values_before(cycle),
                    origin_cycle=rule.introduced,
                )

            ctx.ask_from(rule.introduced, limit)

        ctx.ask_from(
            0,
            lambda c: probes.single(
                rng,
                key="parked_question",
                category=ProbeCategory.ABSTENTION,
                question=f"What did the team decide about {project} {question}?",
                correct=NOT_STATED,
                distractors=[
                    "It was made mandatory",
                    "It was rejected outright",
                    "It was made optional, up to each engineer",
                    "It was approved for next quarter",
                ],
                origin_cycle=0,
                options=profile.options,
            ),
        )

    # -- beats ---------------------------------------------------------------

    def _state_rule(
        self, ctx: BuildContext, rng: Rng, rule: _Rule, *, cycle: int, position: float
    ) -> None:
        t = rule.template
        value = rule.value_at(cycle)
        shown = _shown(t, value, rng, ctx.profile.indirect_rate) if value else None
        phrasing = t.indirect if rng.chance(ctx.profile.indirect_rate) else t.direct
        sentence = _fill(rng.choice(phrasing), ctx.project, shown)
        ctx.state(
            rng,
            cycle,
            position,
            sentence,
            restatement=say(
                ctx,
                rng,
                "constraint.restate",
                _RESTATE,
                rule=lower_first(t.label),
                project=ctx.project,
            ),
        )

    def _place_decoy(
        self, ctx: BuildContext, rng: Rng, decoy: RuleTemplate, *, position: float
    ) -> None:
        project = ctx.project
        value = rng.choice(decoy.values) if decoy.values else None
        kind = rng.choice(("other_scope", "hypothetical", "rejected"))
        if kind == "other_scope":
            other = rng.choice(ctx.setting.other_projects)
            statement = _fill(rng.choice(decoy.direct), other, value)
            ctx.place(
                0,
                position,
                [
                    TurnDraft(
                        TurnRole.USER,
                        say(
                            ctx,
                            rng,
                            "constraint.other_scope",
                            _OTHER_SCOPE,
                            other=other,
                            statement=statement,
                            project=project,
                        ),
                    ),
                    TurnDraft(
                        TurnRole.ASSISTANT,
                        say(
                            ctx,
                            rng,
                            "constraint.other_scope_reply",
                            _OTHER_SCOPE_REPLY,
                            other=other,
                        ),
                    ),
                ],
            )
        elif kind == "hypothetical":
            ctx.place(
                0,
                position,
                [
                    TurnDraft(
                        TurnRole.USER,
                        say(
                            ctx,
                            rng,
                            "constraint.hypothetical",
                            _HYPOTHETICAL,
                            project=project,
                            rule=lower_first(decoy.label),
                        ),
                    ),
                    TurnDraft(
                        TurnRole.ASSISTANT,
                        say(ctx, rng, "constraint.hypothetical_reply", _HYPOTHETICAL_REPLY),
                    ),
                ],
            )
        else:
            person = rng.choice(ctx.setting.cast)
            ctx.place(
                0,
                position,
                [
                    TurnDraft(
                        TurnRole.USER,
                        say(
                            ctx,
                            rng,
                            "constraint.proposal",
                            _PROPOSAL,
                            name=person.name,
                            rule=lower_first(decoy.label),
                            project=project,
                        ),
                    ),
                    TurnDraft(
                        TurnRole.ASSISTANT,
                        say(ctx, rng, "constraint.proposal_reply", _PROPOSAL_REPLY),
                    ),
                    TurnDraft(
                        TurnRole.USER, say(ctx, rng, "constraint.proposal_declined", _DECLINED)
                    ),
                ],
            )

    def _change(
        self,
        ctx: BuildContext,
        rng: Rng,
        real: list[_Rule],
        spare: list[RuleTemplate],
        cycle: int,
        position: float,
    ) -> None:
        project = ctx.project
        # State as of this cycle, so a second move builds on the first.
        active = [r for r in real if r.active(cycle)]
        valued = [r for r in active if r.template.values and len(r.template.values) > 1]

        def has_active_peer(rule: _Rule) -> bool:
            # Each probe group keeps a rule in force, so "none of these apply" never
            # becomes an answer an empty context would get right.
            start = real.index(rule) // _GROUP * _GROUP
            return any(p is not rule and p.active(cycle) for p in real[start : start + _GROUP])

        liftable = [r for r in active if has_active_peer(r)]
        options = ["add"] if spare else []
        if liftable:
            options.append("lift")
        if valued:
            options.append("value")
        if not options:
            return
        move = rng.choice(options)
        if move == "add":
            template = spare.pop(0)
            rule = _Rule(template, introduced=cycle)
            if template.values:
                rule.values[cycle] = rng.choice(template.values)
            real.append(rule)
            self._state_rule(ctx, rng, rule, cycle=cycle, position=position)
        elif move == "lift":
            rule = rng.choice(liftable)
            rule.lifted = cycle
            ctx.state(
                rng,
                cycle,
                position,
                say(
                    ctx,
                    rng,
                    "constraint.lifted",
                    _LIFTED,
                    project=project,
                    rule=lower_first(rule.template.label),
                    reason=say(ctx, rng, "constraint.lift_reason", _LIFT_REASONS),
                ),
                restatement=say(
                    ctx, rng, "constraint.lifted_restate", _LIFTED_RESTATE, project=project
                ),
            )
        else:
            rule = rng.choice(valued)
            old = rule.value_at(cycle)
            new = rng.choice([v for v in rule.template.values if v != old])
            rule.values[cycle] = new
            shown = _shown(rule.template, new, rng, ctx.profile.indirect_rate)
            ctx.state(
                rng,
                cycle,
                position,
                say(
                    ctx,
                    rng,
                    "constraint.limit_changed",
                    _LIMIT_CHANGED,
                    statement=_fill(rng.choice(rule.template.direct), project, shown),
                ),
                restatement=say(ctx, rng, "constraint.limit_changed_restate", _LIMIT_RESTATE),
            )


register_family(BuriedConstraint())
