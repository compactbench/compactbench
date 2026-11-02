"""Conditional scope: rules that cover only some components, or only until a date.

What it tests:

- Does the artifact keep a rule's *scope*, not just the rule? "No deploys to
  the billing service and the export job until March 30" is a different fact
  from "no deploys".
- Does it follow scope changes across cycles — a component added to the
  freeze, another released from it, a window that ends?
- Does it keep exact end dates?
- Does it keep this project's policy apart from a look-alike policy on a
  sibling project that covers other components?
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import ClassVar

from compactbench.contracts import Probe, ProbeCategory, ValueKind
from compactbench.scenarios import probes
from compactbench.scenarios.builder import BuildContext
from compactbench.scenarios.families.base import (
    Family,
    human_date,
    register_family,
    say,
    spread,
)
from compactbench.scenarios.lexicon import ScopedPolicy
from compactbench.scenarios.rng import Rng

_EPOCH = date(2026, 1, 1)
_ADDED = ("The {label} now covers the {component} too.", "Add the {component} to the {label}.")
_REMOVED = (
    "The {component} is out of the {label} as of today.",
    "We're releasing the {component} from the {label}.",
)
_ENDED = ("The {label} is over — it no longer applies to anything.",)
_EXTENDED = ("The {label} is extended to {date}.",)
_SIBLING = ("Separate thing: {other} has its own {label}, covering {targets}. Not ours.",)
_RESTATE = ("Noted — {label} scope updated.",)
_RESTATE_INITIAL = ("Noted — the {label} covers {targets}.",)


_ENDED_ANSWER = "Nothing: it has ended"


def _still(items: Iterable[str]) -> str:
    return f"It still covers {_join(sorted(items))}"


def _join(items: list[str]) -> str:
    named = [f"the {i}" for i in items]
    if len(named) == 1:
        return named[0]
    return ", ".join(named[:-1]) + " and " + named[-1]


@dataclass
class _Policy:
    template: ScopedPolicy
    scope: dict[int, frozenset[str]] = field(default_factory=dict[int, frozenset[str]])
    """Components covered from each cycle on; an empty set means the policy ended."""
    until: dict[int, str] = field(default_factory=dict[int, str])

    def covered(self, cycle: int) -> frozenset[str]:
        current: frozenset[str] = frozenset()
        for start in sorted(self.scope):
            if start <= cycle:
                current = self.scope[start]
        return current

    def ever(self, cycle: int) -> frozenset[str]:
        out: set[str] = set()
        for start, comps in self.scope.items():
            if start <= cycle:
                out |= comps
        return frozenset(out)

    def end_date(self, cycle: int) -> str | None:
        current: str | None = None
        for start in sorted(self.until):
            if start <= cycle:
                current = self.until[start]
        return current


class ConditionalScope(Family):
    key: ClassVar[str] = "conditional_scope"
    version: ClassVar[str] = "1.0.0"
    title: ClassVar[str] = "Conditional scope"
    description: ClassVar[str] = (
        "Rules that cover only some components or only until a date, whose scope "
        "widens, narrows and ends across cycles, next to look-alike policies for "
        "sibling projects."
    )

    def build(self, ctx: BuildContext) -> None:
        rng = ctx.rng
        profile = ctx.profile
        setting = ctx.setting
        project = ctx.project
        components = list(setting.components)
        templates = rng.sample(
            setting.lexicon.scoped_policies,
            min(max(2, profile.items // 2), len(setting.lexicon.scoped_policies)),
        )
        policies = [_Policy(t) for t in templates]
        sibling_scope: dict[str, list[str]] = {}

        for policy, pos in zip(
            policies, spread(rng.child("pos"), len(policies), 0.03, 0.8), strict=True
        ):
            r = rng.child(f"policy:{policy.template.key}")
            size = r.randint(2, min(4, len(components) - 1))
            scope = r.sample(components, size)
            policy.scope[0] = frozenset(scope)
            fields: dict[str, object] = {"project": project, "targets": _join(scope)}
            if policy.template.dated:
                until = (_EPOCH + timedelta(days=r.randint(60, 300))).isoformat()
                policy.until[0] = until
                fields["date"] = human_date(until, r, profile.indirect_rate)
            ctx.state(
                r,
                0,
                pos,
                r.choice(policy.template.statements).format(**fields),
                restatement=say(
                    ctx,
                    r,
                    "scope.restate_initial",
                    _RESTATE_INITIAL,
                    label=policy.template.label,
                    targets=_join(scope),
                ),
            )
            if r.chance(profile.decoy_rate):
                other = r.choice(setting.other_projects)
                elsewhere = r.sample(
                    [c for c in components if c not in scope], min(2, len(components) - size)
                )
                sibling_scope[policy.template.key] = elsewhere
                ctx.state(
                    r,
                    0,
                    r.uniform(0.05, 0.95),
                    say(
                        ctx,
                        r,
                        "scope.sibling",
                        _SIBLING,
                        other=other,
                        label=policy.template.label,
                        targets=_join(elsewhere),
                    ),
                )

        for cycle in range(1, ctx.drift_cycles + 1):
            r = rng.child(f"cycle:{cycle}")
            if not r.chance(profile.change_rate):
                continue
            moves = 2 if profile.items >= 8 else 1
            for index, pos in enumerate(spread(r.child("pos"), moves, 0.1, 0.9)):
                self._change(ctx, r.child(f"move:{index}"), policies, components, cycle, pos)

        for policy in policies:
            self._ask(ctx, policy, components, sibling_scope.get(policy.template.key, []))

    def _change(
        self,
        ctx: BuildContext,
        rng: Rng,
        policies: list[_Policy],
        components: list[str],
        cycle: int,
        position: float,
    ) -> None:
        # Read the state as of this cycle so a second change to the same policy in
        # one cycle builds on the first instead of overwriting it.
        live = [p for p in policies if p.covered(cycle)]
        if not live:
            return
        policy = rng.choice(live)
        covered = set(policy.covered(cycle))
        label = policy.template.label
        moves = ["add", "remove"] + (["extend"] if policy.template.dated else []) + ["end"]
        move = rng.choice(moves)
        fields: dict[str, object] = {"label": label}
        if move == "add":
            outside = [c for c in components if c not in covered]
            if not outside:
                return
            component = rng.choice(outside)
            covered.add(component)
            fields["component"] = component
            sentence = say(ctx, rng, "scope.added", _ADDED, **fields)
        elif move == "remove" and len(covered) > 1:
            component = rng.choice(sorted(covered))
            covered.discard(component)
            fields["component"] = component
            sentence = say(ctx, rng, "scope.removed", _REMOVED, **fields)
        elif move == "extend" and policy.end_date(cycle):
            old = date.fromisoformat(policy.end_date(cycle) or "")
            new = (old + timedelta(days=rng.randint(7, 60))).isoformat()
            policy.until[cycle] = new
            fields["date"] = human_date(new, rng, ctx.profile.indirect_rate)
            sentence = say(ctx, rng, "scope.extended", _EXTENDED, **fields)
        else:
            covered = set[str]()
            sentence = say(ctx, rng, "scope.ended", _ENDED, **fields)
        policy.scope[cycle] = frozenset(covered)
        ctx.state(
            rng,
            cycle,
            position,
            sentence,
            restatement=say(ctx, rng, "scope.restate", _RESTATE, label=label),
        )

    def _ask(
        self, ctx: BuildContext, policy: _Policy, components: list[str], elsewhere: list[str]
    ) -> None:
        rng = ctx.rng
        label = policy.template.label
        project = ctx.project

        def coverage(cycle: int) -> Probe:
            covered = sorted(policy.covered(cycle))
            if not covered:
                return ended(cycle)
            dropped = sorted(policy.ever(cycle) - policy.covered(cycle))
            return probes.multi(
                rng,
                key=f"scope_{policy.template.key}",
                category=ProbeCategory.CONSTRAINT_APPLICATION,
                question=(
                    f"Which of these {project} components does the {label} cover right now? "
                    "Select every one (none, if it no longer applies)."
                ),
                correct=covered,
                stale=dropped,
                traps=elsewhere,
                wrong=components,
                origin_cycle=0,
                max_options=ctx.profile.options + 1,
            )

        def ended(cycle: int) -> Probe:
            # "It has ended" is a positive answer, so an empty context can't score it
            # the way it would score an empty selection.
            last = next(
                (policy.scope[s] for s in sorted(policy.scope, reverse=True) if policy.scope[s]),
                frozenset[str](),
            )
            r = rng.child(f"ended:{policy.template.key}:{cycle}")
            fillers = [
                _still(r.sample(components, r.randint(1, min(3, len(components)))))
                for _ in range(ctx.profile.options * 2)
            ]
            return probes.single(
                rng,
                key=f"scope_{policy.template.key}",
                category=ProbeCategory.CONSTRAINT_APPLICATION,
                question=f"What does {project}'s {label} cover right now?",
                correct=_ENDED_ANSWER,
                stale=[_still(last)] if last else [],
                traps=[_still(elsewhere)] if elsewhere else [],
                distractors=fillers,
                origin_cycle=0,
                options=ctx.profile.options,
            )

        ctx.ask_from(0, coverage)
        if policy.template.dated:

            def until(cycle: int) -> Probe | None:
                end = policy.end_date(cycle)
                if end is None or not policy.covered(cycle):
                    return None
                earlier = [d for c, d in policy.until.items() if c <= cycle and d != end]
                return probes.value(
                    key=f"until_{policy.template.key}",
                    category=ProbeCategory.CONSTRAINT_RECALL,
                    question=f"Until what date does {project}'s {label} run?",
                    answer=end,
                    kind=ValueKind.DATE,
                    stale=earlier,
                    origin_cycle=0,
                )

            ctx.ask_from(0, until)


register_family(ConditionalScope())
