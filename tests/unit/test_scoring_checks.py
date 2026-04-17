"""Unit tests for individual check functions + dispatch."""

from __future__ import annotations

import pytest

from compactbench.scoring import (
    ScoringError,
    contains_normalized,
    exact,
    forbidden_absent,
    run_check,
    set_match,
)

pytestmark = pytest.mark.unit


class TestContainsNormalized:
    def test_substring_match(self) -> None:
        assert contains_normalized("hello", "say hello world") == 1.0

    def test_case_insensitive(self) -> None:
        assert contains_normalized("HELLO", "say hello world") == 1.0

    def test_whitespace_tolerant(self) -> None:
        assert contains_normalized("hello  world", "HELLO world") == 1.0

    def test_no_match(self) -> None:
        assert contains_normalized("quick brown fox", "lazy dog") == 0.0

    def test_empty_expected_always_matches(self) -> None:
        assert contains_normalized("", "anything") == 1.0


class TestForbiddenAbsent:
    def test_absent_scores_one(self) -> None:
        assert forbidden_absent("use eval()", "we should parse the input carefully") == 1.0

    def test_present_scores_zero(self) -> None:
        assert forbidden_absent("use eval()", "let's use eval() on the input") == 0.0

    def test_case_insensitive(self) -> None:
        assert forbidden_absent("eval", "using EVAL now") == 0.0

    def test_empty_forbidden_never_violates(self) -> None:
        assert forbidden_absent("", "anything") == 1.0


class TestExact:
    def test_matches_on_equality(self) -> None:
        assert exact("42", "42") == 1.0

    def test_strips_whitespace(self) -> None:
        assert exact("hello", "  hello  ") == 1.0

    def test_case_sensitive(self) -> None:
        assert exact("Hello", "hello") == 0.0


class TestSetMatch:
    def test_all_present(self) -> None:
        assert set_match(["apple", "banana"], "banana and apple in a bowl") == 1.0

    def test_partial(self) -> None:
        assert set_match(["apple", "banana", "cherry"], "apple and banana") == pytest.approx(2 / 3)

    def test_none_present(self) -> None:
        assert set_match(["apple", "banana"], "just a dog") == 0.0

    def test_empty_expected_always_matches(self) -> None:
        assert set_match([], "anything") == 1.0


class TestRunCheck:
    def test_dispatches_to_contains_normalized(self) -> None:
        spec = {"check": "contains_normalized", "value": "hello"}
        assert run_check(spec, "say hello world") == 1.0

    def test_dispatches_to_forbidden_absent(self) -> None:
        spec = {"check": "forbidden_absent", "value": "bad"}
        assert run_check(spec, "everything is fine") == 1.0

    def test_dispatches_to_exact(self) -> None:
        spec = {"check": "exact", "value": "42"}
        assert run_check(spec, "42") == 1.0

    def test_dispatches_to_set_match(self) -> None:
        spec = {"check": "set_match", "values": ["a", "b"]}
        assert run_check(spec, "a and b together") == 1.0

    def test_raises_on_missing_check(self) -> None:
        with pytest.raises(ScoringError, match="'check'"):
            run_check({}, "response")

    def test_raises_on_unknown_check(self) -> None:
        with pytest.raises(ScoringError, match="unknown check"):
            run_check({"check": "not_a_real_check"}, "response")

    def test_raises_when_value_wrong_type(self) -> None:
        with pytest.raises(ScoringError, match="string"):
            run_check({"check": "contains_normalized", "value": 42}, "response")

    def test_raises_when_set_match_values_wrong_type(self) -> None:
        with pytest.raises(ScoringError, match="list of strings"):
            run_check({"check": "set_match", "values": "oops"}, "response")
