"""The ranked evaluation script: how the sandbox is pointed at the model proxy."""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

pytestmark = pytest.mark.unit

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "ranked" / "evaluate.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("ranked_evaluate", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


evaluate = _load()


def test_the_sandbox_reaches_the_proxy_by_address() -> None:
    provider, route, env, kind = evaluate.sandbox_setup("anthropic", None, "172.18.0.2")
    assert (provider, route, kind) == ("anthropic", "anthropic", "default")
    assert env["ANTHROPIC_BASE_URL"] == "http://172.18.0.2:8080/anthropic"
    assert env["COMPACTBENCH_ANTHROPIC_API_KEY"] == "sandbox"

    _, route, env, kind = evaluate.sandbox_setup(
        "custom", "https://llm.example.com/v1/", "10.0.0.5"
    )
    assert (route, kind) == ("custom", "custom")
    assert env["COMPACTBENCH_OPENAI_BASE_URL"] == "http://10.0.0.5:8080/custom/v1"


def test_the_proxy_address_is_read_from_the_sandbox_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    networks = {
        "bridge": {"IPAddress": "172.17.0.2"},
        "cb-sandbox-ab12": {"IPAddress": "172.18.0.2"},
    }

    def fake_run(argv: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        assert argv[:2] == ["docker", "inspect"]
        return subprocess.CompletedProcess(argv, 0, stdout=json.dumps(networks) + "\n")

    monkeypatch.setattr(evaluate, "_run", fake_run)
    assert evaluate._proxy_address("cb-proxy-ab12", "cb-sandbox-ab12") == "172.18.0.2"
    with pytest.raises(RuntimeError, match="no address"):
        evaluate._proxy_address("cb-proxy-ab12", "cb-sandbox-other")


def test_a_failed_run_is_described_by_a_fixed_reason_only() -> None:
    reasons = {reason for _, reason in evaluate.FAILURE_REASONS}
    log = "Traceback ...\nSandboxError: method failed: KeyError: 'Priya owns billing'\n"
    assert evaluate.failure_reason(log) == "the method raised an error"
    assert evaluate.failure_reason("sandbox timed out after 900s") in reasons
    assert evaluate.failure_reason("anything else, including case text") == (
        "the evaluation stopped with an error"
    )
    for reason in [*reasons, evaluate.failure_reason("")]:
        assert "Priya" not in reason


def test_published_usage_comes_from_the_proxy_log(tmp_path: Path) -> None:
    log = tmp_path / "calls.jsonl"
    log.write_text(
        "\n".join(
            [
                json.dumps({"status": 200, "input_tokens": 1000, "output_tokens": 50}),
                json.dumps({"status": 200, "input_tokens": 2000, "output_tokens": 70}),
                json.dumps({"status": 429, "input_tokens": 0, "output_tokens": 0}),
                json.dumps({"status": 403, "refused": "model not allowed"}),
                "not json",
            ]
        ),
        encoding="utf-8",
    )
    usage = evaluate.measured_usage(log)
    assert (usage.prompt_tokens, usage.completion_tokens, usage.call_count) == (3000, 120, 2)
    assert evaluate.measured_usage(tmp_path / "missing.jsonl").total_tokens == 0
