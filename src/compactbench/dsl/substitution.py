"""Handlebars-style ``{{variable}}`` substitution."""

from __future__ import annotations

import re

from compactbench.dsl.errors import UnresolvedReferenceError

# Matches {{ name }} or {{name}} or {{ namespace.name }}. Whitespace optional.
_PATTERN = re.compile(r"\{\{\s*([\w.]+)\s*\}\}")


def substitute(text: str, bindings: dict[str, str]) -> str:
    """Replace every ``{{ref}}`` in ``text`` with its binding.

    Raises :class:`UnresolvedReferenceError` if any reference has no binding.
    """

    def _repl(match: re.Match[str]) -> str:
        ref = match.group(1)
        if ref not in bindings:
            raise UnresolvedReferenceError(
                f"no binding for {{{{{ref}}}}}. Known: {sorted(bindings)}"
            )
        return bindings[ref]

    return _PATTERN.sub(_repl, text)


def extract_references(text: str) -> list[str]:
    """Return every ``{{ref}}`` name in ``text`` in order of appearance."""
    return [m.group(1) for m in _PATTERN.finditer(text)]
