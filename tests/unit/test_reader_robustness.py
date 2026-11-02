"""The reader-robustness check: same contexts, a second reader, Kendall's tau."""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

from compactbench.providers import get_provider_cls
from compactbench.runner import RunArgs, run_experiment

pytestmark = pytest.mark.unit
SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "reader_robustness.py"


def _module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("reader_robustness", SCRIPT)
    assert spec
    assert spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses look their module up here
    spec.loader.exec_module(module)
    return module


rr = _module()


def test_kendall_tau_b() -> None:
    a = {"x": 0.9, "y": 0.5, "z": 0.1}
    assert rr.kendall_tau_b(a, a) == 1.0
    assert rr.kendall_tau_b(a, {"x": 0.1, "y": 0.5, "z": 0.9}) == -1.0
    assert 0 < rr.kendall_tau_b(a, {"x": 0.9, "y": 0.1, "z": 0.1}) < 1


def test_rescoring_traced_cases(tmp_path: Path) -> None:
    for method in ("naive-summary", "extractive"):
        asyncio.run(
            run_experiment(
                RunArgs(
                    method_spec=f"built-in:{method}",
                    suite="practice",
                    provider_key="mock",
                    model="mock-deterministic",
                    output_path=tmp_path / f"{method}.jsonl",
                    traces_path=tmp_path / f"{method}.traces.jsonl",
                    cases_per_family=2,
                    drift_cycles=1,
                    budget_tokens=1024,
                )
            )
        )
    items = rr.load_items(tmp_path, cases=1, cycles={0, 1})
    assert {i.method for i in items} == {"naive-summary", "extractive"}
    assert all(
        len({i.case_id for i in items if i.method == m}) == 1
        for m in ("naive-summary", "extractive")
    )
    asyncio.run(rr.rescore(items, get_provider_cls("mock")(), "mock-deterministic", 10**9))
    result = rr.report(items)
    assert set(result["methods"]) == {"naive-summary", "extractive"}
    assert 0.0 <= result["probe_agreement"] <= 1.0
    assert -1.0 <= result["kendall_tau_b"] <= 1.0
