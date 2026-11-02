"""Assemble a family's beats and probes into a full multi-cycle case.

A family describes *what happens*: beats (short runs of turns that state a
rule, make a decision, hand over ownership, or plant a decoy) at relative
positions within a cycle's segment, plus the probes to ask after each
compaction. The builder pads every segment with on-topic filler up to the
profile's token target and numbers the turns.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from compactbench.contracts import CycleSpec, Probe, Turn, TurnRole
from compactbench.rendering import render_turn
from compactbench.scenarios.noise import PUBLIC_NOISE, NoiseSource, TurnDraft
from compactbench.scenarios.profile import Profile
from compactbench.scenarios.rng import Rng
from compactbench.scenarios.world import Setting
from compactbench.tokens import count_tokens

_ACKS = (
    "Got it.",
    "Noted.",
    "Okay, understood.",
    "Makes sense.",
    "Okay.",
    "Understood — carrying on.",
    "Right, thanks.",
)


@dataclass(frozen=True)
class Beat:
    cycle: int
    position: float
    turns: tuple[TurnDraft, ...]


@dataclass
class BuildContext:
    """What a family gets to work with while building one case."""

    rng: Rng
    profile: Profile
    setting: Setting
    drift_cycles: int
    noise: NoiseSource = PUBLIC_NOISE
    beats: list[Beat] = field(default_factory=list[Beat])
    probes: dict[int, list[Probe]] = field(default_factory=dict[int, list[Probe]])

    @property
    def project(self) -> str:
        return self.setting.project

    @property
    def last_cycle(self) -> int:
        return self.drift_cycles

    def place(self, cycle: int, position: float, turns: list[TurnDraft]) -> None:
        """Put ``turns`` at ``position`` (0..1) within cycle ``cycle``'s segment."""
        if not 0 <= cycle <= self.drift_cycles:
            raise ValueError(f"cycle {cycle} outside 0..{self.drift_cycles}")
        self.beats.append(Beat(cycle, min(max(position, 0.0), 1.0), tuple(turns)))

    def state(
        self,
        rng: Rng,
        cycle: int,
        position: float,
        sentence: str,
        *,
        restatement: str | None = None,
        speaker: TurnRole = TurnRole.USER,
    ) -> None:
        """State ``sentence`` in the conversation, buried or plain per the profile.

        ``restatement`` is what the assistant says back when the profile calls
        for a clean restatement; otherwise it gives a generic acknowledgement.
        """
        if speaker == TurnRole.USER and rng.chance(self.profile.embed_rate):
            self.place(cycle, position, self.noise.embed(rng, self.setting, sentence))
            return
        ack = (
            restatement
            if restatement and rng.chance(self.profile.restate_rate)
            else rng.choice(self.setting.lexicon.phrases.get("ack") or _ACKS)
        )
        if speaker == TurnRole.USER:
            turns = [TurnDraft(TurnRole.USER, sentence), TurnDraft(TurnRole.ASSISTANT, ack)]
        else:
            turns = [TurnDraft(speaker, sentence)]
        self.place(cycle, position, turns)

    def ask(self, cycle: int, probe: Probe) -> None:
        """Ask ``probe`` after compaction ``cycle``."""
        if not 0 <= cycle <= self.drift_cycles:
            raise ValueError(f"cycle {cycle} outside 0..{self.drift_cycles}")
        bucket = self.probes.setdefault(cycle, [])
        if any(p.key == probe.key for p in bucket):
            raise ValueError(f"probe {probe.key!r} asked twice at cycle {cycle}")
        bucket.append(probe)

    def ask_from(self, origin: int, make: Callable[[int], Probe | None]) -> None:
        """Ask ``make(cycle)`` after every compaction from ``origin`` to the last.

        ``make`` sees the cycle number and returns the probe as of the end of
        that cycle (or ``None`` to skip it there).
        """
        for cycle in range(origin, self.drift_cycles + 1):
            probe = make(cycle)
            if probe is not None:
                self.ask(cycle, probe)


def keep_probe_subset(ctx: BuildContext, limit: int, rng: Rng, *, default_family: str) -> None:
    """Keep ``limit`` distinct probe keys, split as evenly as possible across families.

    A key is kept or dropped for every cycle, so carried probes stay comparable from
    the first compaction to the last. Families with fewer keys than their share
    give the spare to the others.
    """
    keys: dict[str, set[str]] = {}
    for probes in ctx.probes.values():
        for probe in probes:
            keys.setdefault(probe.family or default_family, set()).add(probe.key)
    remaining = dict(sorted((family, sorted(found)) for family, found in keys.items()))
    quota = dict.fromkeys(remaining, 0)
    budget = max(0, limit)
    while budget and any(len(remaining[f]) > quota[f] for f in remaining):
        open_families = [f for f in remaining if len(remaining[f]) > quota[f]]
        share = max(1, budget // len(open_families))
        for family in open_families:
            take = min(share, len(remaining[family]) - quota[family], budget)
            quota[family] += take
            budget -= take
            if not budget:
                break
    chosen = {
        key
        for family, found in remaining.items()
        for key in rng.child(f"family:{family}").sample(found, quota[family])
    }
    for cycle, probes in ctx.probes.items():
        ctx.probes[cycle] = [p for p in probes if p.key in chosen]


def assemble(ctx: BuildContext, rng: Rng) -> list[CycleSpec]:
    """Turn the context's beats into numbered turns padded to the profile's sizes."""
    specs: list[CycleSpec] = []
    next_id = 0
    for cycle in range(ctx.drift_cycles + 1):
        seg_rng = rng.child(f"segment:{cycle}")
        target = ctx.profile.initial_tokens if cycle == 0 else ctx.profile.cycle_tokens

        opening = _opening(seg_rng, ctx, cycle)
        beats = sorted((b for b in ctx.beats if b.cycle == cycle), key=lambda b: b.position)
        used = _rendered_tokens(opening)
        used += sum(_rendered_tokens(b.turns) for b in beats)

        filler: list[tuple[float, tuple[TurnDraft, ...]]] = []
        while used < target:
            episode = ctx.noise.episode(seg_rng, ctx.setting)
            used += _rendered_tokens(episode)
            filler.append((seg_rng.random(), tuple(episode)))

        timeline = sorted(
            [(b.position, 0, b.turns) for b in beats] + [(pos, 1, turns) for pos, turns in filler],
            key=lambda item: (item[0], item[1]),
        )
        drafts = list(opening) + [t for _, _, turns in timeline for t in turns]
        turns: list[Turn] = []
        for draft in drafts:
            turns.append(
                Turn(
                    id=next_id,
                    role=draft.role,
                    content=draft.content,
                    name=draft.name,
                    tags=list(draft.tags),
                )
            )
            next_id += 1
        specs.append(CycleSpec(cycle=cycle, turns=turns, probes=list(ctx.probes.get(cycle, []))))
    return specs


def _rendered_tokens(drafts: Sequence[TurnDraft]) -> int:
    """Tokens ``drafts`` take once rendered, role labels and separators included.

    Counting content alone undercounts settings whose filler has many short turns,
    so their cases would come out longer than the profile says.
    """
    return sum(
        count_tokens(render_turn(Turn(id=0, role=d.role, content=d.content, name=d.name))) + 1
        for d in drafts
    )


_OPENING = (
    "Hi — I'm {user}, tech lead on {project} at {company}. I'll be working through a bunch "
    "of things with you today, so keep track as we go.",
)
_OPENING_REPLY = ("Sounds good. Where do you want to start?",)
_RESUME = (
    "Back on {project}. Picking up where we left off.",
    "Ok, new session — let's continue.",
    "I'm back. A few things changed since we last talked.",
    "Continuing with {project}.",
)
_RESUME_REPLY = ("Ready when you are.",)


def _opening(rng: Rng, ctx: BuildContext, cycle: int) -> list[TurnDraft]:
    setting = ctx.setting
    phrases = setting.lexicon.phrases
    fields = {"user": setting.user.first, "project": setting.project, "company": setting.company}
    if cycle == 0:
        user, reply = (
            phrases.get("opening") or _OPENING,
            phrases.get("opening_reply") or _OPENING_REPLY,
        )
    else:
        user, reply = phrases.get("resume") or _RESUME, phrases.get("resume_reply") or _RESUME_REPLY
    return [
        TurnDraft(TurnRole.USER, rng.choice(user).format(**fields)),
        TurnDraft(TurnRole.ASSISTANT, rng.choice(reply).format(**fields)),
    ]
