"""Reference resolution: choices made by pointing ("the second one", "the cheaper EU option").

A shortlist is laid out with prices, regions and who recommended what. The
choice is then made by reference rather than by name, and in later cycles it
is changed by reference again ("switch to the runner-up") — which can only be
resolved if the artifact kept the shortlist, not just the pick.

What it tests:

- Does the artifact record the *resolved* choice, not the words used to make it?
- Does it keep the shortlist and its attributes, so later references resolve?
- Does it keep exact prices attached to the right option?
- Does it avoid inventing a choice for a shortlist that was deferred?
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar

from compactbench.contracts import NOT_STATED, Probe, ProbeCategory, TurnRole, ValueKind
from compactbench.scenarios import probes
from compactbench.scenarios.builder import BuildContext
from compactbench.scenarios.families.base import Family, register_family, say, spread
from compactbench.scenarios.noise import TurnDraft
from compactbench.scenarios.rng import Rng
from compactbench.scenarios.world import Person

_PURPOSES = (
    "CDN",
    "error tracking",
    "log archival",
    "load testing",
    "SMS delivery",
    "backup storage",
    "status page",
    "penetration testing",
)
_REGIONS = ("EU", "US", "APAC")
_LINE = ("{ordinal}: {vendor} — {price}/year, hosted in {region}, recommended by {name}",)
_ASK_QUOTES = ("Can you pull the {purpose} quotes?",)
_QUOTES_TOOL = ("Vendor shortlist — {purpose} ({project})\n{lines}",)
_QUOTES_ACK = ("There are {count} quotes on the shortlist.",)
_PASTE = ("Here's the {purpose} shortlist for {project}, in the order we got them:\n{lines}",)
_PASTE_ACK = ("Thanks. Want me to compare them?",)
_PICK = ("For {purpose}, let's go with {phrase}.",)
_PICK_RESTATE = ("Okay — {vendor} for {purpose}.",)
_SWITCH = (
    "Change on the {purpose} vendor: drop {current} and go with {phrase} from the original "
    "shortlist instead.",
)
_SWITCH_RESTATE = ("Switched — {vendor} for {purpose}.",)
_DEFER = ("Let's not pick a {purpose} vendor yet — park it until next quarter.",)
_DEFER_ACK = ("Okay, no decision on that for now.",)
_BY_ORDINAL = ("the {ordinal} quote",)
_BY_RECOMMENDER = ("the one {name} recommended",)
_CHEAPEST = ("the cheapest quote",)
_PRICIEST = ("the most expensive quote",)
_CHEAPER_OF_TWO = ("the cheaper of the two {region}-hosted options",)
_CHEAPEST_IN = ("the cheapest of the {region}-hosted options",)
_ORDINALS = ("first", "second", "third", "fourth")


@dataclass(frozen=True)
class _Quote:
    vendor: str
    price: int
    region: str
    recommended_by: Person


@dataclass
class _Shortlist:
    purpose: str
    quotes: list[_Quote]
    picks: list[tuple[int, str]] = field(default_factory=list[tuple[int, str]])
    """``(cycle, vendor)`` picks in order."""
    deferred: bool = False

    def pick_at(self, cycle: int) -> str | None:
        chosen = [v for c, v in self.picks if c <= cycle]
        return chosen[-1] if chosen else None

    def price_of(self, vendor: str) -> int:
        return next(q.price for q in self.quotes if q.vendor == vendor)


def _money(amount: int) -> str:
    return f"${amount:,}"


class ReferenceResolution(Family):
    key: ClassVar[str] = "reference_resolution"
    version: ClassVar[str] = "2.0.0"
    title: ClassVar[str] = "Reference resolution"
    description: ClassVar[str] = (
        "Choices made and changed by reference — ordinals, superlatives, who "
        "recommended it — that only resolve if the shortlist survives compaction."
    )

    def build(self, ctx: BuildContext) -> None:
        rng = ctx.rng
        profile = ctx.profile
        setting = ctx.setting
        project = ctx.project

        count = max(2, profile.items // 2 + 1)
        pool = tuple(setting.lexicon.phrases.get("reference.purposes") or _PURPOSES)
        purposes = rng.sample(pool, min(count, len(pool)))
        vendors = rng.shuffled(setting.lexicon.vendors)
        positions = spread(rng.child("list-pos"), len(purposes), 0.03, 0.7)

        shortlists: list[_Shortlist] = []
        for index, (purpose, pos) in enumerate(zip(purposes, positions, strict=True)):
            r = rng.child(f"shortlist:{purpose}")
            size = 3 if profile.items < 6 else 4
            names = (
                [vendors.pop() for _ in range(size)]
                if len(vendors) >= size
                else r.sample(setting.lexicon.vendors, size)
            )
            recommenders = r.sample(list(setting.cast), size)
            prices = r.sample(range(6, 60), size)
            quotes = [
                _Quote(name, price * 500, r.choice(_REGIONS), who)
                for name, price, who in zip(names, prices, recommenders, strict=True)
            ]
            shortlist = _Shortlist(purpose, quotes)
            shortlists.append(shortlist)
            self._present(ctx, r, shortlist, pos)

            deferred = index == len(purposes) - 1 and r.chance(profile.decoy_rate * 0.6)
            if deferred:
                shortlist.deferred = True
                ctx.place(
                    0,
                    r.uniform(pos + 0.02, min(pos + 0.2, 0.99)),
                    [
                        TurnDraft(
                            TurnRole.USER, say(ctx, r, "reference.defer", _DEFER, purpose=purpose)
                        ),
                        TurnDraft(
                            TurnRole.ASSISTANT, say(ctx, r, "reference.defer_ack", _DEFER_ACK)
                        ),
                    ],
                )
                continue
            vendor, phrase = self._reference(ctx, r, shortlist, exclude=None)
            shortlist.picks.append((0, vendor))
            fields: dict[str, object] = {"purpose": purpose, "phrase": phrase, "vendor": vendor}
            ctx.state(
                r,
                0,
                r.uniform(pos + 0.03, min(pos + 0.25, 0.99)),
                say(ctx, r, "reference.pick", _PICK, **fields),
                restatement=say(ctx, r, "reference.pick_restate", _PICK_RESTATE, **fields),
            )

        # --- later cycles: switch by reference -------------------------------------
        for cycle in range(1, ctx.drift_cycles + 1):
            r = rng.child(f"switch:{cycle}")
            live = [s for s in shortlists if not s.deferred]
            if not live or not r.chance(profile.change_rate):
                continue
            shortlist = r.choice(live)
            current = shortlist.pick_at(cycle - 1)
            vendor, phrase = self._reference(ctx, r, shortlist, exclude=current)
            shortlist.picks.append((cycle, vendor))
            fields = {
                "purpose": shortlist.purpose,
                "phrase": phrase,
                "vendor": vendor,
                "current": current,
            }
            ctx.state(
                r,
                cycle,
                r.uniform(0.1, 0.9),
                say(ctx, r, "reference.switch", _SWITCH, **fields),
                restatement=say(ctx, r, "reference.switch_restate", _SWITCH_RESTATE, **fields),
            )

        # --- probes -----------------------------------------------------------------
        for index, shortlist in enumerate(shortlists):
            other_vendors = [q.vendor for s in shortlists if s is not shortlist for q in s.quotes]

            def pick(
                cycle: int,
                shortlist: _Shortlist = shortlist,
                extra: list[str] = other_vendors,
                index: int = index,
            ) -> Probe:
                current = shortlist.pick_at(cycle)
                earlier = [v for c, v in shortlist.picks if c <= cycle and v != current]
                return probes.single(
                    rng,
                    key=f"pick_{index}_{shortlist.purpose.replace(' ', '_')}",
                    category=(
                        ProbeCategory.ABSTENTION
                        if shortlist.deferred
                        else ProbeCategory.REFERENCE_RESOLUTION
                    ),
                    question=f"Which vendor did the team pick for {project}'s {shortlist.purpose}?",
                    correct=current or NOT_STATED,
                    stale=earlier,
                    distractors=[q.vendor for q in shortlist.quotes] + extra,
                    origin_cycle=0,
                    options=profile.options,
                )

            ctx.ask_from(0, pick)
            if shortlist.deferred:
                continue

            def price(
                cycle: int, shortlist: _Shortlist = shortlist, index: int = index
            ) -> Probe | None:
                current = shortlist.pick_at(cycle)
                if current is None:
                    return None
                earlier = [
                    _money(shortlist.price_of(v))
                    for c, v in shortlist.picks
                    if c <= cycle and v != current
                ]
                return probes.value(
                    key=f"price_{index}_{shortlist.purpose.replace(' ', '_')}",
                    category=ProbeCategory.FACT_RECALL,
                    question=(
                        f"What is the annual price of the vendor the team picked for {project}'s "
                        f"{shortlist.purpose}?"
                    ),
                    answer=_money(shortlist.price_of(current)),
                    kind=ValueKind.MONEY,
                    stale=earlier,
                    origin_cycle=0,
                )

            ctx.ask_from(0, price)

    # -- beats ---------------------------------------------------------------------

    def _present(self, ctx: BuildContext, rng: Rng, shortlist: _Shortlist, position: float) -> None:
        lines = [
            say(
                ctx,
                rng,
                "reference.line",
                _LINE,
                ordinal=_ORDINALS[i].capitalize(),
                vendor=q.vendor,
                price=_money(q.price),
                region=q.region,
                name=q.recommended_by.name,
            )
            for i, q in enumerate(shortlist.quotes)
        ]
        fields: dict[str, object] = {
            "purpose": shortlist.purpose,
            "project": ctx.project,
            "count": len(lines),
            "lines": "\n".join(lines),
        }
        if rng.chance(0.5):
            turns = [
                TurnDraft(
                    TurnRole.USER, say(ctx, rng, "reference.ask_quotes", _ASK_QUOTES, **fields)
                ),
                TurnDraft(
                    TurnRole.TOOL,
                    say(ctx, rng, "reference.quotes_tool", _QUOTES_TOOL, **fields),
                    name="get_quotes",
                ),
                TurnDraft(
                    TurnRole.ASSISTANT, say(ctx, rng, "reference.quotes_ack", _QUOTES_ACK, **fields)
                ),
            ]
        else:
            turns = [
                TurnDraft(TurnRole.USER, say(ctx, rng, "reference.paste", _PASTE, **fields)),
                TurnDraft(
                    TurnRole.ASSISTANT, say(ctx, rng, "reference.paste_ack", _PASTE_ACK, **fields)
                ),
            ]
        ctx.place(0, position, turns)

    @staticmethod
    def _reference(
        ctx: BuildContext, rng: Rng, shortlist: _Shortlist, *, exclude: str | None
    ) -> tuple[str, str]:
        """Pick a vendor and an unambiguous way of referring to it without its name."""
        quotes = shortlist.quotes
        candidates: list[tuple[str, str]] = []
        for i, q in enumerate(quotes):
            candidates.append(
                (q.vendor, say(ctx, rng, "reference.by_ordinal", _BY_ORDINAL, ordinal=_ORDINALS[i]))
            )
            candidates.append(
                (
                    q.vendor,
                    say(
                        ctx,
                        rng,
                        "reference.by_recommender",
                        _BY_RECOMMENDER,
                        name=q.recommended_by.name,
                    ),
                )
            )
        by_price = sorted(quotes, key=lambda q: q.price)
        candidates.append((by_price[0].vendor, say(ctx, rng, "reference.cheapest", _CHEAPEST)))
        candidates.append((by_price[-1].vendor, say(ctx, rng, "reference.priciest", _PRICIEST)))
        for region in _REGIONS:
            in_region = sorted((q for q in quotes if q.region == region), key=lambda q: q.price)
            if len(in_region) == 2:
                candidates.append(
                    (
                        in_region[0].vendor,
                        say(ctx, rng, "reference.cheaper_of_two", _CHEAPER_OF_TWO, region=region),
                    )
                )
            elif len(in_region) > 2:
                candidates.append(
                    (
                        in_region[0].vendor,
                        say(ctx, rng, "reference.cheapest_in", _CHEAPEST_IN, region=region),
                    )
                )
        usable = [c for c in candidates if c[0] != exclude]
        return rng.choice(usable)


register_family(ReferenceResolution())
