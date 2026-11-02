"""Case generation: scenario families, difficulty profiles, and suites.

A *family* describes one kind of compaction failure. Given a seed and a
difficulty it produces a :class:`~compactbench.contracts.GeneratedCase`: a
long conversation split into cycles, plus structured probes to ask after each
compaction. A *suite* is a versioned set of families at one difficulty.
"""

from compactbench.scenarios.families import (
    PUBLIC_FAMILIES,
    Family,
    UnknownFamilyError,
    get_family,
    list_families,
    register_family,
)
from compactbench.scenarios.generate import (
    MAX_DRIFT_CYCLES,
    PUBLIC_SETTING,
    SUITES,
    SettingPack,
    Suite,
    expand_suite,
    generate_case,
    get_suite,
    load_suite_pack,
    register_suite,
)
from compactbench.scenarios.lexicon import (
    PUBLIC_LEXICON,
    DecisionTopic,
    FactTemplate,
    Lexicon,
    RuleTemplate,
    ScopedPolicy,
)
from compactbench.scenarios.noise import PUBLIC_NOISE, NoiseSource, TurnDraft
from compactbench.scenarios.profile import PROFILES, Difficulty, Profile
from compactbench.scenarios.rng import Rng
from compactbench.scenarios.world import Person, Setting

__all__ = [
    "MAX_DRIFT_CYCLES",
    "PROFILES",
    "PUBLIC_FAMILIES",
    "PUBLIC_LEXICON",
    "PUBLIC_NOISE",
    "PUBLIC_SETTING",
    "SUITES",
    "DecisionTopic",
    "Difficulty",
    "FactTemplate",
    "Family",
    "Lexicon",
    "NoiseSource",
    "Person",
    "Profile",
    "Rng",
    "RuleTemplate",
    "ScopedPolicy",
    "Setting",
    "SettingPack",
    "Suite",
    "TurnDraft",
    "UnknownFamilyError",
    "expand_suite",
    "generate_case",
    "get_family",
    "get_suite",
    "list_families",
    "load_suite_pack",
    "register_family",
    "register_suite",
]
