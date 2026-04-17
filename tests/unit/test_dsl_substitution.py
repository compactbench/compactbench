"""Tests for {{variable}} substitution."""

from __future__ import annotations

import pytest

from compactbench.dsl import UnresolvedReferenceError, extract_references, substitute

pytestmark = pytest.mark.unit


def test_substitute_simple() -> None:
    assert substitute("hello {{name}}", {"name": "world"}) == "hello world"


def test_substitute_multiple_refs() -> None:
    text = "{{a}} and {{b}}"
    bindings = {"a": "X", "b": "Y"}
    assert substitute(text, bindings) == "X and Y"


def test_substitute_same_ref_multiple_times() -> None:
    text = "{{x}} {{x}} {{x}}"
    assert substitute(text, {"x": "hi"}) == "hi hi hi"


def test_substitute_tolerates_whitespace_inside_braces() -> None:
    assert substitute("{{ name }}", {"name": "Z"}) == "Z"
    assert substitute("{{  a  }}", {"a": "Q"}) == "Q"


def test_substitute_preserves_non_matching_text() -> None:
    assert substitute("no refs here", {"x": "1"}) == "no refs here"


def test_substitute_raises_on_missing_binding() -> None:
    with pytest.raises(UnresolvedReferenceError):
        substitute("hello {{missing}}", {})


def test_substitute_allows_dotted_names() -> None:
    assert (
        substitute("value: {{difficulty.distractor_turns}}", {"difficulty.distractor_turns": "5"})
        == "value: 5"
    )


def test_extract_references_returns_in_order() -> None:
    assert extract_references("{{b}} then {{a}} then {{c}}") == ["b", "a", "c"]


def test_extract_references_returns_duplicates() -> None:
    assert extract_references("{{x}} {{y}} {{x}}") == ["x", "y", "x"]


def test_extract_references_empty_when_no_refs() -> None:
    assert extract_references("plain text") == []
