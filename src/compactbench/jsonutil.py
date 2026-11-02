"""Lenient JSON recovery for model output.

Models wrap JSON in prose ("Here is the state:"), code fences, and reasoning
preambles. Treating those as unparsable would measure the parser instead of
the method or the reader, and worst on exactly the small and local models the
benchmark should be runnable on.
"""

from __future__ import annotations

import json
from typing import Any, cast


def load_json_object(text: str) -> dict[str, Any] | None:
    """Return the first JSON object in ``text``, or ``None`` if there isn't one."""
    cleaned = strip_code_fences(strip_reasoning_blocks(text))
    try:
        data: Any = json.loads(cleaned)
    except json.JSONDecodeError:
        extracted = extract_first_json_object(cleaned)
        if extracted is None:
            return None
        try:
            data = json.loads(extracted)
        except json.JSONDecodeError:
            return None
    if not isinstance(data, dict):
        return None
    return cast("dict[str, Any]", data)


def strip_reasoning_blocks(text: str) -> str:
    """Drop ``<think>``-style reasoning preambles some models emit before the answer.

    These arrive ahead of the JSON and are not part of it. Removing them here
    keeps the fence/decoder path below simple.
    """
    out = text
    for tag in ("think", "thinking", "reasoning"):
        open_tag, close_tag = f"<{tag}>", f"</{tag}>"
        while open_tag in out and close_tag in out:
            start = out.index(open_tag)
            end = out.index(close_tag, start) + len(close_tag)
            out = out[:start] + out[end:]
    return out


def extract_first_json_object(text: str) -> str | None:
    """Return the first balanced ``{...}`` span in ``text``, or None.

    Brace-counting is string- and escape-aware, so a ``}`` inside a value (very
    common — forbidden behaviours quote code) does not terminate the object
    early. Deliberately simple: it recovers the overwhelmingly common
    "prose around one object" shape without pulling in a JSON5 dependency.
    """
    start = text.find("{")
    if start == -1:
        return None

    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None


def strip_code_fences(text: str) -> str:
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
