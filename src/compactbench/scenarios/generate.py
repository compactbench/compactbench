"""Generate cases from families, and expand suites into case lists."""

from __future__ import annotations

import dataclasses
import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path

from compactbench.contracts import GeneratedCase
from compactbench.scenarios.builder import BuildContext, assemble, keep_probe_subset
from compactbench.scenarios.families import PUBLIC_FAMILIES, Family, get_family
from compactbench.scenarios.lexicon import PUBLIC_LEXICON, Lexicon
from compactbench.scenarios.noise import PUBLIC_NOISE, NoiseSource
from compactbench.scenarios.profile import PROFILES, Difficulty
from compactbench.scenarios.rng import Rng, derive_case_seed, derive_seed
from compactbench.scenarios.world import build_setting

MAX_DRIFT_CYCLES = 8


@dataclass(frozen=True)
class SettingPack:
    """A world a case can take place in: its vocabulary, phrasing and filler."""

    name: str
    lexicon: Lexicon
    noise: NoiseSource


PUBLIC_SETTING = SettingPack("software", PUBLIC_LEXICON, PUBLIC_NOISE)


def generate_case(
    family: str | Family,
    seed: int,
    difficulty: Difficulty,
    *,
    suite: str = "adhoc",
    drift_cycles: int | None = None,
    setting: SettingPack = PUBLIC_SETTING,
    probes: int | None = None,
) -> GeneratedCase:
    """Build one case. Pure: the same arguments always give the same case.

    ``probes`` keeps that many distinct probes per case (family-balanced, asked at
    every cycle they apply to) instead of all of them.
    """
    fam = get_family(family) if isinstance(family, str) else family
    profile = PROFILES[difficulty]
    if fam.min_lookalikes > profile.lookalikes:
        profile = dataclasses.replace(profile, lookalikes=fam.min_lookalikes)
    cycles = profile.drift_cycles if drift_cycles is None else drift_cycles
    if not 0 <= cycles <= MAX_DRIFT_CYCLES:
        raise ValueError(f"drift_cycles must be between 0 and {MAX_DRIFT_CYCLES}, got {cycles}")

    rng = Rng(seed)
    world = build_setting(rng.child("setting"), setting.lexicon, profile)
    ctx = BuildContext(
        rng=rng.child("family"),
        profile=profile,
        setting=world,
        drift_cycles=cycles,
        noise=setting.noise,
    )
    fam.build(ctx)
    if probes is not None:
        keep_probe_subset(ctx, probes, rng.child("probe-subset"), default_family=fam.key)
    specs = assemble(ctx, rng.child("assemble"))
    return GeneratedCase(
        case_id=f"{fam.key}-{difficulty.value}-c{cycles}-{seed:016x}",
        family=fam.key,
        family_version=fam.version,
        suite=suite,
        seed=seed,
        difficulty=difficulty.value,
        setting=setting.name,
        cycles=specs,
    )


@dataclass(frozen=True)
class Suite:
    """A named, versioned set of families at one difficulty."""

    key: str
    version: str
    description: str
    families: tuple[str, ...]
    difficulty: Difficulty
    cases_per_family: int
    settings: tuple[SettingPack, ...] = (PUBLIC_SETTING,)
    """Worlds the suite's cases are spread across, chosen per case by its seed."""
    probes_per_case: int | None = None
    """Distinct probes kept per case (family-balanced); ``None`` keeps them all.

    Score variance comes mostly from case to case, so many cases with a subset of
    probes each are more stable than a few cases with every probe, at the same
    reader cost."""

    @property
    def label(self) -> str:
        return f"{self.key}@{self.version}"


SUITES: dict[str, Suite] = {
    "starter": Suite(
        key="starter",
        version="2.0.1",
        description="Short cases (~1.5k tokens) for smoke-testing a method end to end.",
        families=PUBLIC_FAMILIES,
        difficulty=Difficulty.EASY,
        cases_per_family=2,
    ),
    "practice": Suite(
        key="practice",
        version="2.0.1",
        description=(
            "Public twin of the ranked Elite set: mixed sessions with every family in one "
            "conversation, at Elite difficulty, in the public world (~32k-token openings, "
            "4 drift cycles, 48 cases of 20 probes; use --cases for a quicker look)."
        ),
        families=("mixed",),
        difficulty=Difficulty.ELITE,
        cases_per_family=48,
        probes_per_case=20,
    ),
    "drills": Suite(
        key="drills",
        version="2.0.1",
        description=(
            "One family per case at Elite difficulty, for working on one failure mode at a time."
        ),
        families=PUBLIC_FAMILIES,
        difficulty=Difficulty.ELITE,
        cases_per_family=2,
    ),
}


def register_suite(suite: Suite) -> Suite:
    SUITES[suite.key] = suite
    return suite


def get_suite(key: str) -> Suite:
    suite = SUITES.get(key)
    if suite is None:
        raise KeyError(f"unknown suite {key!r}. Known: {sorted(SUITES)}")
    return suite


def expand_suite(
    suite: Suite,
    *,
    seed_group: str = "default",
    cases_per_family: int | None = None,
    difficulty: Difficulty | None = None,
    drift_cycles: int | None = None,
) -> list[GeneratedCase]:
    """Every case in ``suite`` for ``seed_group``, in a stable order.

    The seed for case ``slot`` of a family is derived from the suite label, the
    family key and version, the seed group and the slot — so two families never
    share variable choices, and a new seed group is a fresh sample of the same
    distribution.
    """
    level = difficulty or suite.difficulty
    count = suite.cases_per_family if cases_per_family is None else cases_per_family
    cases: list[GeneratedCase] = []
    for key in suite.families:
        family = get_family(key)
        namespace = f"{suite.label}/{family.key}@{family.version}/{level.value}"
        for slot in range(count):
            seed = derive_case_seed(namespace, seed_group, slot)
            pick = derive_seed(seed, "setting") % len(suite.settings)
            cases.append(
                generate_case(
                    family,
                    seed,
                    level,
                    suite=suite.key,
                    drift_cycles=drift_cycles,
                    setting=suite.settings[pick],
                    probes=suite.probes_per_case,
                )
            )
    return cases


def load_suite_pack(path: Path) -> list[Suite]:
    """Import a private suite pack and register the suites (and families) it defines.

    A pack is a Python file that registers its own families with
    :func:`compactbench.scenarios.register_family` on import and exposes a
    module-level ``SUITES`` list. Ranked evaluation uses packs so the hidden
    generators and vocabulary never live in the public package.
    """
    spec = importlib.util.spec_from_file_location(f"_compactbench_pack_{path.stem}", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"could not load suite pack from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    raw: object = getattr(module, "SUITES", None)
    if not isinstance(raw, list | tuple):
        raise ImportError(f"suite pack {path} must define a SUITES list")
    suites: list[Suite] = []
    for item in raw:  # pyright: ignore[reportUnknownVariableType]
        if not isinstance(item, Suite):
            raise ImportError(f"suite pack {path}: SUITES entries must be Suite instances")
        suites.append(register_suite(item))
    return suites
