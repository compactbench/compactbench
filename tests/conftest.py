"""Shared pytest fixtures."""

from __future__ import annotations

import pytest


@pytest.fixture
def deterministic_seed() -> int:
    """Fixed seed used by generation determinism tests."""
    return 42
