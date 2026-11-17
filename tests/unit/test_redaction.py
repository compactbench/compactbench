"""Public copies of results files keep every score and drop everything private."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from compactbench.redaction import is_redacted, redact_results
from compactbench.runner import RunArgs, run_experiment, to_run_result

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def results(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("run") / "r.jsonl"
    asyncio.run(
        run_experiment(
            RunArgs(
                method_spec="built-in:naive-summary",
                suite="practice",
                provider_key="mock",
                model="mock-deterministic",
                output_path=out,
                cases_per_family=2,
                drift_cycles=2,
                budget_tokens=1024,
            )
        )
    )
    return out


def test_redaction_keeps_every_metric(results: Path, tmp_path: Path) -> None:
    public = tmp_path / "public.jsonl"
    redact_results(results, public)
    before, after = to_run_result(results), to_run_result(public)
    assert after.metrics == before.metrics
    assert [c.score for c in after.cases] == [c.score for c in before.cases]
    assert not is_redacted(results)
    assert is_redacted(public)


def test_no_private_key_or_warning_text_survives(results: Path, tmp_path: Path) -> None:
    raw = results.read_text(encoding="utf-8")
    keys = {
        p["key"]
        for line in raw.splitlines()
        if (e := json.loads(line)).get("event") == "case_complete"
        for c in e["case_result"]["cycles"]
        for p in c["probe_results"]
    }
    public = tmp_path / "public.jsonl"
    redact_results(results, public)
    text = public.read_text(encoding="utf-8")
    for key in keys:
        assert key.split("/", 1)[-1] not in text
    assert "trimmed to fit" not in text


def test_salts_make_runs_unlinkable(results: Path, tmp_path: Path) -> None:
    a, b = tmp_path / "a.jsonl", tmp_path / "b.jsonl"
    redact_results(results, a)
    redact_results(results, b)
    assert a.read_text() != b.read_text()
    redact_results(results, tmp_path / "d.jsonl", salt=b"fixed")
    redact_results(results, tmp_path / "e.jsonl", salt=b"fixed")
    assert (tmp_path / "d.jsonl").read_text() == (tmp_path / "e.jsonl").read_text()


PUBLIC_SUITES = {"starter", "practice", "drills"}
ROOT = Path(__file__).resolve().parents[2]


def test_published_hidden_set_results_are_redacted() -> None:
    """Guard: no results file from a hidden suite lands in the repository unredacted."""
    from compactbench.runner.persistence import read_run_start

    files = [*ROOT.glob("baselines/*/*.jsonl"), *ROOT.glob("submissions/*/*/results.jsonl")]
    for path in files:
        try:
            start = read_run_start(path)
        except ValueError:
            continue  # pre-v2 archives
        if start is not None and start.suite not in PUBLIC_SUITES:
            assert is_redacted(path), f"{path.relative_to(ROOT)} has private keys or method text"


def test_published_usage_is_the_proxy_measurement(results: Path, tmp_path: Path) -> None:
    from compactbench.contracts import TokenUsage
    from compactbench.leaderboard.projection import project_row

    measured = TokenUsage(prompt_tokens=1003, completion_tokens=101, call_count=7)
    out = tmp_path / "public.jsonl"
    redact_results(results, out, compactor_usage=measured)
    run = to_run_result(out)
    cycles = [cycle for case in run.cases for cycle in case.cycles]
    assert sum(c.compactor_usage.prompt_tokens for c in cycles if c.compactor_usage) == 1003
    assert sum(c.compactor_usage.completion_tokens for c in cycles if c.compactor_usage) == 101
    assert sum(c.compactor_usage.call_count for c in cycles if c.compactor_usage) == 7
    shares = {c.compactor_usage.total_tokens for c in cycles if c.compactor_usage}
    assert max(shares) - min(shares) <= 2, "spread evenly, so nothing can be encoded in it"
    for case in run.cases:
        expected = sum(
            (
                part.total_tokens
                for c in case.cycles
                for part in (c.compactor_usage, c.reader_usage, c.control_usage)
                if part
            ),
            0,
        )
        assert case.token_usage is not None
        assert case.token_usage.total_tokens == expected
    row = project_row(run, handle="a", org=None, published_at=datetime(2026, 11, 17, tzinfo=UTC))
    assert row["method_tokens"] == 1104
    original = to_run_result(results)
    assert row["score"] == original.metrics.score
