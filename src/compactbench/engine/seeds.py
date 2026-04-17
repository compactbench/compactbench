"""Seed derivation for case generation.

A *case seed* is derived from ``(suite_version, seed_group, case_slot)`` via
SHA-256. This is the seed that downstream :mod:`compactbench.dsl.generators`
uses to resolve template variables.

Stable across Python versions and platforms: the derivation uses UTF-8 byte
encoding, SHA-256, and a big-endian integer decode of the leading 8 bytes.
"""

from __future__ import annotations

import hashlib


def derive_case_seed(suite_version: str, seed_group: str, case_slot: int) -> int:
    """Derive a deterministic seed for a specific case slot.

    Parameters
    ----------
    suite_version:
        Identifier of the benchmark suite version (e.g. ``"starter@1.0.0"``).
    seed_group:
        Identifier of the seed group within this suite version
        (e.g. ``"default"`` or ``"elite_ranked_q1"``).
    case_slot:
        Zero-based case slot index.
    """
    payload = f"{suite_version}:{seed_group}:{case_slot}".encode()
    digest = hashlib.sha256(payload).digest()
    return int.from_bytes(digest[:8], "big", signed=False)
