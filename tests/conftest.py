"""Shared pytest fixtures."""

from __future__ import annotations

import os

import pytest


@pytest.fixture
def deterministic_seed() -> int:
    """Fixed seed used by generation determinism tests."""
    return 42


@pytest.fixture(autouse=True)
def _isolate_compactbench_env(  # pyright: ignore[reportUnusedFunction]
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Clear every ``COMPACTBENCH_*`` variable for the duration of each test.

    Provider constructors read configuration straight from ``os.environ``, so
    without this a developer's own shell leaks into the suite. The concrete case
    that motivated it: exporting ``COMPACTBENCH_OPENAI_BASE_URL`` (exactly what
    someone running a local vLLM server does) makes the API key optional, and
    ``test_requires_api_key`` — which only clears the key — then fails for a
    reason that has nothing to do with the code under test. CI never sees it
    because CI has a clean environment, so it only ever bites contributors.

    Individual tests that need a variable set should ``monkeypatch.setenv`` it;
    this fixture runs first, so those still work.
    """
    for name in [k for k in os.environ if k.startswith("COMPACTBENCH_")]:
        monkeypatch.delenv(name, raising=False)
