"""Running a method in a sandboxed process over the line protocol."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from compactbench.contracts import CompactionRequest, Turn, TurnRole
from compactbench.runner import RunArgs, run_experiment, to_run_result
from compactbench.sandbox import Sandbox, SandboxedCompactor, SandboxError, usage_counter

pytestmark = pytest.mark.unit

# The same CLI entry point the container runs, as a local process.
LOCAL = Sandbox(command=(sys.executable, "-m"), timeout_seconds=30)


def _request() -> CompactionRequest:
    return CompactionRequest(
        cycle=0, turns=[Turn(id=0, role=TurnRole.USER, content="Deploy freeze until Friday.")]
    )


async def test_compacts_through_the_sandbox() -> None:
    usage = usage_counter()
    compactor = SandboxedCompactor(
        LOCAL,
        method_spec="built-in:naive-summary",
        provider_key="mock",
        model="mock-deterministic",
        usage=usage,
    )
    try:
        hello = await compactor.start()
        assert hello.name == "naive-summary"
        artifact = await compactor.compact(_request())
        # The mock model writes nothing; what matters is the round trip and the usage.
        assert artifact.method_metadata["model"] == "mock-deterministic"
        assert (await usage.snapshot()).call_count >= 1
    finally:
        await compactor.aclose()


async def test_method_output_on_stdout_does_not_break_the_protocol(tmp_path: Path) -> None:
    method = tmp_path / "noisy.py"
    method.write_text(
        "from compactbench.compactors import Compactor\n"
        "from compactbench.contracts import CompactionArtifact\n"
        "class Noisy(Compactor):\n"
        "    name = 'noisy'\n"
        "    version = '1.0.0'\n"
        "    async def compact(self, request):\n"
        "        print('debug output that would corrupt the channel')\n"
        "        return CompactionArtifact(summaryText='kept')\n",
        encoding="utf-8",
    )
    compactor = SandboxedCompactor(
        LOCAL, method_spec=f"{method}:Noisy", provider_key="mock", model="mock-deterministic"
    )
    try:
        artifact = await compactor.compact(_request())
        assert artifact.summary_text == "kept"
    finally:
        await compactor.aclose()


async def test_method_errors_are_reported(tmp_path: Path) -> None:
    method = tmp_path / "broken.py"
    method.write_text(
        "from compactbench.compactors import Compactor\n"
        "class Broken(Compactor):\n"
        "    name = 'broken'\n"
        "    version = '1.0.0'\n"
        "    async def compact(self, request):\n"
        "        raise RuntimeError('nope')\n",
        encoding="utf-8",
    )
    compactor = SandboxedCompactor(
        LOCAL, method_spec=f"{method}:Broken", provider_key="mock", model="mock-deterministic"
    )
    try:
        with pytest.raises(SandboxError, match="nope"):
            await compactor.compact(_request())
    finally:
        await compactor.aclose()


async def test_a_sandbox_that_never_starts_is_an_error() -> None:
    compactor = SandboxedCompactor(
        Sandbox(command=(sys.executable, "-c", "import sys; sys.exit(3)", "--")),
        method_spec="built-in:null",
        provider_key="mock",
        model="m",
    )
    with pytest.raises(SandboxError):
        await compactor.start()
    await compactor.aclose()


async def test_a_whole_run_through_the_sandbox(tmp_path: Path) -> None:
    out = tmp_path / "r.jsonl"
    await run_experiment(
        RunArgs(
            method_spec="built-in:naive-summary",
            suite="starter",
            provider_key="mock",
            model="mock-deterministic",
            output_path=out,
            cases_per_family=1,
            concurrency=2,
            sandbox=LOCAL,
        )
    )
    result = to_run_result(out)
    assert result.method_name == "naive-summary"
    assert result.compactor_endpoint_kind == "default"
    assert len(result.cases) == 8


async def test_a_sandboxed_run_is_recorded_under_the_declared_name(tmp_path: Path) -> None:
    out = tmp_path / "r.jsonl"
    await run_experiment(
        RunArgs(
            method_spec="built-in:naive-summary",
            suite="starter",
            provider_key="mock",
            model="mock-deterministic",
            output_path=out,
            cases_per_family=1,
            sandbox=LOCAL,
            declared_method=("acme-ledger", "2.1.0"),
        )
    )
    result = to_run_result(out)
    assert (result.method_name, result.method_version) == ("acme-ledger", "2.1.0")
