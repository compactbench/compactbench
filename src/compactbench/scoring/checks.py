"""Individual check implementations used by the scorer.

Each check maps a (spec, response) pair to a score in ``[0.0, 1.0]``.
Higher is better. Strings are normalized by lowercasing and collapsing
runs of whitespace so minor formatting differences don't spuriously fail.
"""

from __future__ import annotations

import re
from typing import Any

from compactbench.scoring.errors import ScoringError

_WHITESPACE = re.compile(r"\s+")


def _normalize(text: str) -> str:
    """Lowercase + collapse whitespace for tolerant substring comparison."""
    return _WHITESPACE.sub(" ", text.strip().lower())


def contains_normalized(expected: str, response: str) -> float:
    """1.0 if the normalized ``expected`` is a substring of the normalized ``response``."""
    if not expected:
        return 1.0
    return 1.0 if _normalize(expected) in _normalize(response) else 0.0


def forbidden_absent(forbidden: str, response: str) -> float:
    """1.0 if ``forbidden`` does NOT appear in ``response`` (normalized)."""
    if not forbidden:
        return 1.0
    return 0.0 if _normalize(forbidden) in _normalize(response) else 1.0


def exact(expected: str, response: str) -> float:
    """1.0 if stripped ``expected`` equals stripped ``response`` (case-sensitive)."""
    return 1.0 if expected.strip() == response.strip() else 0.0


def set_match(expected_items: list[str], response: str) -> float:
    """Fraction of ``expected_items`` that appear (normalized) in ``response``."""
    if not expected_items:
        return 1.0
    norm = _normalize(response)
    matches = sum(1 for item in expected_items if _normalize(item) in norm)
    return matches / len(expected_items)


def run_check(spec: dict[str, Any], response: str) -> float:
    """Dispatch on ``spec['check']`` and run the corresponding check.

    Raises :class:`ScoringError` for missing or unknown check types.
    """
    check_type = spec.get("check")
    if not check_type:
        raise ScoringError("expected spec is missing a 'check' key")

    if check_type == "contains_normalized":
        value = spec.get("value", "")
        if not isinstance(value, str):
            raise ScoringError("'contains_normalized' requires 'value' to be a string")
        return contains_normalized(value, response)

    if check_type == "forbidden_absent":
        value = spec.get("value", "")
        if not isinstance(value, str):
            raise ScoringError("'forbidden_absent' requires 'value' to be a string")
        return forbidden_absent(value, response)

    if check_type == "exact":
        value = spec.get("value", "")
        if not isinstance(value, str):
            raise ScoringError("'exact' requires 'value' to be a string")
        return exact(value, response)

    if check_type == "set_match":
        raw = spec.get("values", [])
        if not isinstance(raw, list):
            raise ScoringError("'set_match' requires 'values' to be a list of strings")
        values: list[str] = []
        for v in raw:  # pyright: ignore[reportUnknownVariableType]
            if not isinstance(v, str):
                raise ScoringError("'set_match' requires 'values' to be a list of strings")
            values.append(v)
        return set_match(values, response)

    raise ScoringError(
        f"unknown check type {check_type!r}. "
        f"Known: ['contains_normalized', 'forbidden_absent', 'exact', 'set_match']"
    )
