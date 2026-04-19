"""Arithmetic and semantics of the :class:`TokenUsage` contract."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from compactbench.contracts import TokenUsage

pytestmark = pytest.mark.unit


def test_default_is_all_zero() -> None:
    u = TokenUsage()
    assert u.prompt_tokens == 0
    assert u.completion_tokens == 0
    assert u.cached_prompt_tokens == 0
    assert u.call_count == 0
    assert u.total_tokens == 0


def test_total_tokens_sums_prompt_and_completion() -> None:
    u = TokenUsage(prompt_tokens=100, completion_tokens=40, call_count=1)
    assert u.total_tokens == 140


def test_cached_tokens_are_not_double_counted_in_total() -> None:
    u = TokenUsage(prompt_tokens=100, completion_tokens=0, cached_prompt_tokens=80, call_count=1)
    assert u.total_tokens == 100


def test_addition_is_element_wise() -> None:
    a = TokenUsage(prompt_tokens=100, completion_tokens=30, cached_prompt_tokens=10, call_count=1)
    b = TokenUsage(prompt_tokens=50, completion_tokens=20, cached_prompt_tokens=0, call_count=2)
    total = a + b
    assert total.prompt_tokens == 150
    assert total.completion_tokens == 50
    assert total.cached_prompt_tokens == 10
    assert total.call_count == 3


def test_addition_returns_a_new_instance() -> None:
    a = TokenUsage(prompt_tokens=1, completion_tokens=1, call_count=1)
    b = TokenUsage(prompt_tokens=2, completion_tokens=2, call_count=1)
    total = a + b
    assert total is not a
    assert total is not b
    assert a.prompt_tokens == 1
    assert b.prompt_tokens == 2


def test_is_frozen() -> None:
    u = TokenUsage(prompt_tokens=1, completion_tokens=1, call_count=1)
    with pytest.raises(ValidationError, match="frozen"):
        u.prompt_tokens = 999  # type: ignore[misc]


def test_rejects_negative_values() -> None:
    with pytest.raises(ValidationError):
        TokenUsage(prompt_tokens=-1)
    with pytest.raises(ValidationError):
        TokenUsage(completion_tokens=-1)
    with pytest.raises(ValidationError):
        TokenUsage(cached_prompt_tokens=-1)
    with pytest.raises(ValidationError):
        TokenUsage(call_count=-1)
