"""Seeded random generators for template variables.

Each generator is a deterministic function of a seed. Sub-seeds are derived
from ``(base_seed, variable_name)`` via SHA-256 so adding or reordering
variables in a template never changes the output of unchanged variables.
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from compactbench.dsl.errors import UnknownGeneratorError
from compactbench.dsl.models import VariableDeclaration


def derive_seed(base_seed: int, variable_name: str) -> int:
    """Derive a deterministic sub-seed for a named variable.

    Uses SHA-256 of ``"{base}:{name}"``. Stable across Python versions.
    """
    payload = f"{base_seed}:{variable_name}".encode()
    digest = hashlib.sha256(payload).digest()
    return int.from_bytes(digest[:8], "big", signed=False)


@runtime_checkable
class Generator(Protocol):
    """Protocol every generator must satisfy."""

    name: str

    def generate(self, seed: int) -> str: ...


@dataclass
class LexiconGenerator:
    """Picks one item from a bounded lexicon, deterministically by seed."""

    name: str
    lexicon: tuple[str, ...]

    def generate(self, seed: int) -> str:
        rng = random.Random(seed)
        return rng.choice(self.lexicon)


@dataclass
class DateGenerator:
    """Generates an ISO-8601 date within a bounded year range."""

    name: str = "date_iso"
    start_year: int = 2024
    end_year: int = 2026

    def generate(self, seed: int) -> str:
        rng = random.Random(seed)
        year = rng.randint(self.start_year, self.end_year)
        month = rng.randint(1, 12)
        day = rng.randint(1, 28)
        return f"{year:04d}-{month:02d}-{day:02d}"


@dataclass
class AmountGenerator:
    """Generates a USD amount string like ``$47,250``."""

    name: str = "amount_usd"
    magnitudes: tuple[int, ...] = field(default=(2, 3, 4, 5))

    def generate(self, seed: int) -> str:
        rng = random.Random(seed)
        magnitude = rng.choice(self.magnitudes)
        low = 10 ** (magnitude - 1)
        high = 10**magnitude - 1
        amount = rng.randint(low, high)
        return f"${amount:,}"


@dataclass
class SkuGenerator:
    """Generates an alphanumeric SKU like ``SKU-AB9421``."""

    name: str = "product_sku"

    def generate(self, seed: int) -> str:
        rng = random.Random(seed)
        prefix = rng.choice(("SKU", "PRD", "ITEM", "ART"))
        alpha = "".join(rng.choices("ABCDEFGHJKLMNPQRTUVWXYZ", k=2))
        num = rng.randint(100, 9999)
        return f"{prefix}-{alpha}{num}"


# --- lexicons ------------------------------------------------------------

_FIRST_NAMES: tuple[str, ...] = (
    "Alice",
    "Bob",
    "Carol",
    "David",
    "Elena",
    "Farid",
    "Grace",
    "Hassan",
    "Iris",
    "Julia",
    "Kenji",
    "Leo",
    "Maya",
    "Noor",
    "Omar",
    "Priya",
    "Quinn",
    "Rafael",
    "Sofia",
    "Tara",
    "Umar",
    "Vera",
    "Wen",
    "Xiu",
    "Yusuf",
    "Zara",
    "Aditya",
    "Bianca",
    "Chen",
    "Dimitri",
    "Esha",
    "Fatima",
    "Gabriel",
    "Hana",
    "Ivy",
    "Jamal",
)

_ACTION_PHRASES: tuple[str, ...] = (
    "use regex to parse HTML",
    "store passwords in plaintext",
    "deploy on Fridays",
    "skip code review",
    "hardcode API keys in source",
    "use floats for money",
    "ignore rate limits",
    "trust user input without validation",
    "log personally identifiable information to stdout",
    "cache forever without an invalidation strategy",
    "mutate shared global state",
    "catch exceptions silently",
    "call eval() on user input",
    "commit directly to the main branch",
    "build SQL through string concatenation",
    "run schema migrations inside a web request",
    "hold database locks during outbound HTTP calls",
    "retry non-idempotent operations",
    "disable TLS certificate verification",
    "commit credentials to git history",
    "use md5 to hash passwords",
    "trust the X-Forwarded-For header blindly",
    "disable CSRF tokens",
    "return raw exception messages to end users",
    "assume the server timezone is UTC without configuring it",
)

_PROJECT_NOUNS: tuple[str, ...] = (
    "auth rewrite",
    "pricing revamp",
    "dashboard migration",
    "CI overhaul",
    "onboarding redesign",
    "billing audit",
    "observability pass",
    "search relevance upgrade",
    "webhook refactor",
    "legacy deprecation",
    "mobile launch",
    "integration sprint",
    "performance tune-up",
    "schema migration",
    "feature flag cleanup",
    "access control review",
    "data pipeline rebuild",
    "admin tools revamp",
    "notifications unification",
    "reports module",
)

_ORG_NAMES: tuple[str, ...] = (
    "Acme Systems",
    "Blue Harbor Inc",
    "Cobalt Labs",
    "Delta Fleet",
    "Evergreen Co",
    "Fulcrum Group",
    "Granite Works",
    "Harbor Line",
    "Ironmask Ltd",
    "Juniper Partners",
    "Kestrel and Sons",
    "Linden Row",
    "Meridian Works",
    "Nimbus Group",
    "Orion Bearing",
    "Pioneer Cast",
    "Quartz Rail",
    "Redwood Signals",
    "Starboard Inc",
    "Timberline Holdings",
)


_REGISTRY: dict[str, Generator] = {
    "person_name": LexiconGenerator(name="person_name", lexicon=_FIRST_NAMES),
    "action_phrase": LexiconGenerator(name="action_phrase", lexicon=_ACTION_PHRASES),
    "project_noun": LexiconGenerator(name="project_noun", lexicon=_PROJECT_NOUNS),
    "org_name": LexiconGenerator(name="org_name", lexicon=_ORG_NAMES),
    "date_iso": DateGenerator(),
    "amount_usd": AmountGenerator(),
    "product_sku": SkuGenerator(),
}


def get_generator(name: str) -> Generator:
    """Return the registered generator with ``name`` or raise."""
    gen = _REGISTRY.get(name)
    if gen is None:
        raise UnknownGeneratorError(f"unknown generator {name!r}. Known: {sorted(_REGISTRY)}")
    return gen


def registered_generators() -> tuple[str, ...]:
    """Sorted tuple of registered generator names."""
    return tuple(sorted(_REGISTRY))


def resolve_variables(declarations: list[VariableDeclaration], base_seed: int) -> dict[str, str]:
    """Resolve declared variables into concrete seeded values."""
    resolved: dict[str, str] = {}
    for decl in declarations:
        gen = get_generator(decl.generator)
        sub_seed = derive_seed(base_seed, decl.name)
        resolved[decl.name] = gen.generate(sub_seed)
    return resolved
