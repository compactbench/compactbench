"""scripts/rebuild_leaderboard.py: published submissions become leaderboard rows."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

from compactbench.runner import RunArgs, run_experiment
from compactbench.scenarios import expand_suite, get_suite
from tests.helpers import AnswerKeyReader

pytestmark = pytest.mark.unit


def _script() -> ModuleType:
    path = Path(__file__).resolve().parents[2] / "scripts" / "rebuild_leaderboard.py"
    spec = importlib.util.spec_from_file_location("rebuild_leaderboard", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


async def test_submission_json_supplies_handle_and_model_label(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    method_dir = tmp_path / "submissions" / "alice" / "ledger"
    method_dir.mkdir(parents=True)
    await run_experiment(
        RunArgs(
            method_spec="built-in:naive-summary",
            suite="starter",
            provider_key="mock",
            model="ft-7b",
            output_path=method_dir / "results.jsonl",
            cases_per_family=1,
        ),
        reader_provider=AnswerKeyReader(expand_suite(get_suite("starter"), cases_per_family=1)),
    )
    (method_dir / "submission.json").write_text(
        json.dumps({"handle": "alice", "model_label": "Acme Recall v2"}), encoding="utf-8"
    )
    script = _script()
    monkeypatch.setattr(script, "SUBMISSIONS_DIR", tmp_path / "submissions")
    warnings: list[str] = []
    rows = script._submission_rows(warnings)  # pyright: ignore[reportPrivateUsage]
    assert warnings == []
    assert len(rows) == 1
    assert rows[0]["handle"] == "alice"
    assert rows[0]["model_label"] == "Acme Recall v2"
    assert rows[0]["compactor_model"] == "ft-7b"
