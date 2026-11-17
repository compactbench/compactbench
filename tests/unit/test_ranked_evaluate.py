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


class _ProxyStartedError(Exception):
    pass


def test_the_proxy_gets_only_this_runs_key_never_the_season_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from compactbench.sealing import generate_keypair, seal
    from compactbench.submission import method_key_context, reader_key_context

    season_private, season_public = generate_keypair()
    _, trace_public = generate_keypair()
    bundle = {
        "id": "abc123def456",
        "season": "s1",
        "handle": "alice",
        "github_id": 42,
        "method_name": "ledger",
        "method_version": "1.0.0",
        "class_name": "Ledger",
        "provider": "openrouter",
        "model": "qwen/qwen3-235b",
        "method_py": "class Ledger: ...\n",
        "requirements": "",
        "sealed_method_key": seal(
            season_public, b"sk-or-method", context=method_key_context("s1", "abc123def456")
        ),
        "sealed_reader_key": seal(
            season_public, b"sk-ant-reader", context=reader_key_context("s1", "abc123def456")
        ),
        "created_at": "2026-11-01T00:00:00Z",
    }
    (tmp_path / "bundle.json").write_text(json.dumps(bundle), encoding="utf-8")
    seen: dict[str, Any] = {}

    def fake_run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if argv[:3] == ["docker", "run", "-d"]:
            seen["argv"], seen["env"] = argv, kwargs.get("env") or {}
            raise _ProxyStartedError
        return subprocess.CompletedProcess(argv, 0, stdout="")

    def quiet_run(argv: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(argv, 0, stdout="")

    monkeypatch.setattr(evaluate, "_run", fake_run)
    monkeypatch.setattr(evaluate.subprocess, "run", quiet_run)
    monkeypatch.setenv("COMPACTBENCH_SEASON_PRIVATE_KEY", season_private)
    monkeypatch.setenv("COMPACTBENCH_TRACE_PUBLIC_KEY", trace_public)
    root = Path(__file__).resolve().parents[2]
    monkeypatch.setattr(
        "sys.argv",
        [
            "evaluate.py",
            "--bundle",
            str(tmp_path / "bundle.json"),
            "--image",
            "cb-submission",
            "--proxy-image",
            "cb-proxy",
            "--season",
            str(root / "seasons" / "s1.yaml"),
            "--suite-pack",
            str(tmp_path / "pack.py"),
            "--out",
            str(tmp_path / "out"),
        ],
    )
    with pytest.raises(_ProxyStartedError):
        evaluate.main()
    argv, env = seen["argv"], seen["env"]
    assert env["COMPACTBENCH_PROXY_KEY"] == "sk-or-method"
    assert not any(k.startswith("COMPACTBENCH_") and k != "COMPACTBENCH_PROXY_KEY" for k in env)
    assert season_private not in " ".join(argv)
    assert "sk-or-method" not in " ".join(argv), (
        "the key is passed by name, not on the command line"
    )
    assert "--sealed-key" not in argv
    for flag in ("--read-only", "no-new-privileges"):
        assert flag in argv
    assert argv[argv.index("--cap-drop") + 1] == "ALL"
