"""Case-seed derivation tests."""

from __future__ import annotations

import pytest

from compactbench.engine import derive_case_seed

pytestmark = pytest.mark.unit


def test_derive_case_seed_is_deterministic() -> None:
    a = derive_case_seed("starter@1.0.0", "default", 0)
    b = derive_case_seed("starter@1.0.0", "default", 0)
    assert a == b


def test_derive_case_seed_differs_by_suite_version() -> None:
    a = derive_case_seed("starter@1.0.0", "default", 0)
    b = derive_case_seed("starter@1.0.1", "default", 0)
    assert a != b


def test_derive_case_seed_differs_by_seed_group() -> None:
    a = derive_case_seed("starter@1.0.0", "default", 0)
    b = derive_case_seed("starter@1.0.0", "elite_q1", 0)
    assert a != b


def test_derive_case_seed_differs_by_case_slot() -> None:
    a = derive_case_seed("starter@1.0.0", "default", 0)
    b = derive_case_seed("starter@1.0.0", "default", 1)
    assert a != b


def test_derive_case_seed_fits_in_64_bits() -> None:
    s = derive_case_seed("starter@1.0.0", "default", 99)
    assert 0 <= s < 2**64
