"""The Hugging Face export of the public suites."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest
from ruamel.yaml import YAML

from compactbench.contracts.case import GeneratedCase
from compactbench.scenarios import expand_suite, get_suite

pytestmark = pytest.mark.unit


def _script() -> ModuleType:
    path = Path(__file__).parents[2] / "scripts" / "hf_dataset.py"
    spec = importlib.util.spec_from_file_location("hf_dataset", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_a_record_is_the_case_run_uses_with_a_string_seed() -> None:
    script = _script()
    suite = get_suite("starter")
    case = expand_suite(suite, seed_group=script.SEED_GROUP)[0]
    record = json.loads(json.dumps(script.case_record(case, suite.version)))
    assert isinstance(record["seed"], str)
    assert record["suite_version"] == suite.version
    restored = GeneratedCase.model_validate(
        {**{k: v for k, v in record.items() if k != "suite_version"}, "seed": int(record["seed"])}
    )
    assert restored == case


def test_the_card_declares_one_config_per_suite() -> None:
    script = _script()
    stats = {key: {"cases": 1, "compactions": 2, "questions": 3} for key in script.SUITES}
    text = script.card(stats)
    meta = YAML(typ="safe").load(text.split("---")[1])
    configs = {c["config_name"]: c for c in meta["configs"]}
    assert set(configs) == set(script.SUITES)
    assert configs["practice"].get("default") is True
    assert configs["drills"]["data_files"] == "data/drills-*.jsonl"
    assert meta["license"] == "apache-2.0"


def test_big_suites_are_split_into_shards_under_the_limit(tmp_path: Path) -> None:
    script = _script()
    lines = [json.dumps({"i": i, "pad": "x" * 3_000_000}) + "\n" for i in range(5)]
    paths = script.write_shards(tmp_path, "practice", lines)
    assert [p.name for p in paths] == [
        "practice-00000-of-00003.jsonl",
        "practice-00001-of-00003.jsonl",
        "practice-00002-of-00003.jsonl",
    ]
    assert all(p.stat().st_size <= script.MAX_SHARD_BYTES for p in paths)
    rows = [json.loads(line)["i"] for p in paths for line in p.read_text().splitlines()]
    assert rows == [0, 1, 2, 3, 4]
