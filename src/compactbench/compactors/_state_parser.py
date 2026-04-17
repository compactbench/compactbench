"""Shared JSON-to-StructuredState parser.

Several built-in compactors (structured-state, hierarchical-summary,
hybrid-ledger) ask the model to return a JSON object shaped like
:class:`StructuredState`. This module parses those responses leniently:

- Strips common LLM wrappers (``\\`\\`\\`json`` fences).
- Coerces missing sections to empty collections.
- Filters non-string values out of lists and the entity map.
- Returns any issues as warnings rather than raising, so a single bad field
  doesn't discard the rest of the state.
"""

from __future__ import annotations

import json
from typing import Any, cast

from compactbench.contracts import StructuredState

_LIST_SECTIONS = (
    "immutable_facts",
    "locked_decisions",
    "deferred_items",
    "forbidden_behaviors",
    "unresolved_items",
)

_MAX_SECTION_ITEMS = 200
_MAX_STRING_LENGTH = 500


def parse_state(text: str) -> tuple[StructuredState, list[str]]:
    """Parse a JSON-object response into a :class:`StructuredState` and warnings."""
    warnings: list[str] = []
    cleaned = _strip_code_fences(text)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        warnings.append(f"response was not valid JSON: {exc}")
        return StructuredState(), warnings

    if not isinstance(data, dict):
        warnings.append(f"expected JSON object, got {type(data).__name__}; treating as empty state")
        return StructuredState(), warnings

    obj = cast("dict[str, Any]", data)
    sections: dict[str, Any] = {
        name: _clean_list(obj.get(name), name, warnings) for name in _LIST_SECTIONS
    }
    sections["entity_map"] = _clean_entity_map(obj.get("entity_map"), warnings)
    return StructuredState.model_validate(sections), warnings


def _strip_code_fences(text: str) -> str:
    """Remove ``\\`\\`\\`json`` fences or leading/trailing backticks if present."""
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    # Find the first newline after the opening fence.
    after_fence = stripped[3:]
    if after_fence.lower().startswith("json"):
        after_fence = after_fence[4:]
    if "\n" in after_fence:
        after_fence = after_fence.split("\n", 1)[1]
    # Strip trailing closing fence if present.
    if after_fence.rstrip().endswith("```"):
        after_fence = after_fence.rstrip()[:-3]
    return after_fence.strip()


def _clean_list(value: Any, name: str, warnings: list[str]) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        warnings.append(f"{name!r} was not a list (got {type(value).__name__}); dropping")
        return []
    items = cast("list[Any]", value)
    result: list[str] = []
    for i, item in enumerate(items):
        if not isinstance(item, str):
            warnings.append(f"{name}[{i}] was not a string (got {type(item).__name__}); skipping")
            continue
        item = item.strip()
        if not item:
            continue
        if len(item) > _MAX_STRING_LENGTH:
            warnings.append(f"{name}[{i}] exceeded {_MAX_STRING_LENGTH} chars; truncating")
            item = item[:_MAX_STRING_LENGTH]
        result.append(item)
        if len(result) >= _MAX_SECTION_ITEMS:
            warnings.append(f"{name} exceeded {_MAX_SECTION_ITEMS} items; dropping the rest")
            break
    return result


def _clean_entity_map(value: Any, warnings: list[str]) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        warnings.append(f"'entity_map' was not a mapping (got {type(value).__name__}); dropping")
        return {}
    mapping = cast("dict[Any, Any]", value)
    result: dict[str, str] = {}
    for k, v in mapping.items():
        if not isinstance(k, str) or not isinstance(v, str):
            warnings.append(f"entity_map entry {k!r}={v!r} is not string-to-string; skipping")
            continue
        k = k.strip()
        v = v.strip()
        if not k or not v:
            continue
        if len(k) > _MAX_STRING_LENGTH:
            k = k[:_MAX_STRING_LENGTH]
        if len(v) > _MAX_STRING_LENGTH:
            v = v[:_MAX_STRING_LENGTH]
        result[k] = v
    return result
