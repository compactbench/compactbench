"""Cost projection."""

from __future__ import annotations

import pytest

from compactbench.runner.estimate import estimate_run, format_estimate
from compactbench.scenarios import expand_suite, get_suite

pytestmark = pytest.mark.unit


def _cases():
    return expand_suite(get_suite("starter"), cases_per_family=1)


def test_counts_every_party() -> None:
    est = estimate_run(
        _cases(),
        provider_key="anthropic",
        model="claude-haiku-5-5",
        reader_provider_key="anthropic",
        reader_model="claude-haiku-5-5",
        budget_tokens=1024,
        controls=True,
    )
    cycles = sum(len(c.cycles) for c in _cases())
    assert est.compactor.calls == cycles
    assert est.reader.calls >= cycles
    assert est.controls is not None
    assert est.controls.calls == 2 * est.reader.calls
    assert est.compactor.cost_usd is not None
    report = format_estimate(est)
    assert "Estimated total" in report
    assert "Controls" in report


def test_unknown_model_has_no_price() -> None:
    est = estimate_run(
        _cases(),
        provider_key="mock",
        model="nothing",
        reader_provider_key="mock",
        reader_model="nothing",
        budget_tokens=None,
        controls=False,
    )
    assert est.compactor.cost_usd is None
    assert est.controls is None
    assert "no price" in format_estimate(est)
