"""Mixed session: every family at once, in one long conversation.

Real agent sessions don't stick to one kind of state. Rules, decisions,
ownership, exact figures, ticket status, scoped policies, choices made by
reference and claims from fetched documents all pile up in the same
conversation, and the artifact has to keep all of them within one budget.

What it tests, beyond what each family tests on its own:

- **Prioritization under a budget.** A mixed case carries several times the
  state of a single-family case, so an artifact that spends its budget on prose
  runs out of room; one that records state tersely doesn't.
- **Keeping kinds of state apart.** The same people decide things, own
  components and hold tickets, and the same components carry policies and
  owners, so a lossy artifact attaches facts to the wrong thing.

Each member family builds its part of the case with its own random stream; the
parts are interleaved by position. Probe keys are prefixed with the member's
key and tagged with its family, so scores still break down per family.
Members that draw facts from the same vocabulary pool get disjoint shares of
it.
"""

from __future__ import annotations

import dataclasses
from collections import defaultdict
from typing import ClassVar

from compactbench.scenarios.builder import BuildContext
from compactbench.scenarios.families.base import Family, get_family
from compactbench.scenarios.world import Setting


class MixedSession(Family):
    key: ClassVar[str] = "mixed"
    version: ClassVar[str] = "1.0.0"
    title: ClassVar[str] = "Mixed session"
    description: ClassVar[str] = (
        "Every family in one conversation: rules, decisions, people, figures, tickets, "
        "scoped policies, references and untrusted documents, all under one budget."
    )
    min_lookalikes: ClassVar[int] = 1

    def __init__(self, members: tuple[str, ...]) -> None:
        self.members = members

    def build(self, ctx: BuildContext) -> None:
        settings = self._member_settings(ctx)
        for key in self.members:
            member = get_family(key)
            sub = BuildContext(
                rng=ctx.rng.child(f"member:{key}"),
                profile=ctx.profile,
                setting=settings[key],
                drift_cycles=ctx.drift_cycles,
                noise=ctx.noise,
            )
            member.build(sub)
            ctx.beats.extend(sub.beats)
            for cycle, probes in sub.probes.items():
                for probe in probes:
                    ctx.ask(
                        cycle,
                        probe.model_copy(update={"key": f"{key}/{probe.key}", "family": key}),
                    )
        # Interleave the families' questions so a reader batch isn't all one kind.
        for cycle, probes in ctx.probes.items():
            ctx.probes[cycle] = ctx.rng.child(f"order:{cycle}").shuffled(probes)

    def _member_settings(self, ctx: BuildContext) -> dict[str, Setting]:
        """Each member's view of the world: shared cast and project, disjoint pools."""
        lexicon = ctx.setting.lexicon
        users: dict[str, list[str]] = defaultdict(list)
        for key in self.members:
            for pool in get_family(key).pools:
                users[pool].append(key)
        shares: dict[str, dict[str, tuple[object, ...]]] = defaultdict(dict)
        for pool, keys in users.items():
            items: tuple[object, ...] = getattr(lexicon, pool)
            dealt = ctx.rng.child(f"pool:{pool}").shuffled(list(items))
            for index, key in enumerate(keys):
                shares[key][pool] = tuple(dealt[index :: len(keys)])
        settings: dict[str, Setting] = {}
        for key in self.members:
            if shares[key]:
                own = dataclasses.replace(lexicon, **shares[key])  # pyright: ignore[reportArgumentType]
                settings[key] = dataclasses.replace(ctx.setting, lexicon=own)
            else:
                settings[key] = ctx.setting
        return settings
