"""The MCP self-test data: questions with letters, answer keys kept apart."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

from compactbench.scenarios import expand_suite, get_suite

pytestmark = pytest.mark.unit


def _script() -> ModuleType:
    path = Path(__file__).parents[2] / "scripts" / "selftest_cases.py"
    spec = importlib.util.spec_from_file_location("selftest_cases", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_each_key_matches_a_question_and_its_letters() -> None:
    script = _script()
    case = expand_suite(get_suite("practice"), seed_group="selftest-test", cases_per_family=1)[0]
    public, keys = script._case(case, "full-1", "full")
    questions = {q["id"]: q for c in public["cycles"] for q in c["questions"]}
    assert set(keys) == set(questions)
    assert len(public["cycles"]) == len(case.cycles)
    for qid, key in keys.items():
        question = questions[qid]
        letters = {o.split(".", 1)[0] for o in question["options"]}
        assert set(key["answer"]) <= letters
        assert key["format"] == question["format"] in ("single", "multi")
        assert "answer" not in question
    assert all(isinstance(c["turns"], str) and c["turns"] for c in public["cycles"])
