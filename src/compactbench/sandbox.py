"""Run a compaction method in a sandbox, one request at a time over stdin/stdout.

Ranked evaluation never imports submitted code into the harness. The method
runs in its own process — in practice a locked-down container with no network
except the model proxy — and the harness talks to it over a line protocol:

    harness → sandbox   {"type": "compact", "request": <CompactionRequest>}
    sandbox → harness   {"type": "hello", "protocol": 1, "name": ..., "version": ...}
                        {"type": "artifact", "artifact": <CompactionArtifact>, "usage": <TokenUsage>}
                        {"type": "error", "error": "..."}

The sandbox sees one case at a time and only what a compactor normally sees:
the new turns and its own previous artifact. The hidden suite pack, the probes,
the reader and every other case stay with the harness. Everything the sandbox
sends back is treated as untrusted data and validated before use.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, ClassVar, TextIO

from pydantic import ValidationError

from compactbench.compactors import Compactor
from compactbench.contracts import CompactionArtifact, CompactionRequest, TokenUsage
from compactbench.providers import CompletionRequest, CompletionResponse, CountingProvider, Provider

PROTOCOL = 1
_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.+_-]{0,31}$")


class SandboxError(RuntimeError):
    """The sandboxed method failed, misbehaved, or broke the protocol."""


@dataclass(frozen=True)
class Hello:
    name: str
    version: str


@dataclass(frozen=True)
class Sandbox:
    """How to launch the sandboxed method.

    ``command`` starts a process in the sandbox; ``compactbench sandbox-serve``
    and the method arguments are appended to it. :meth:`docker` builds a
    hardened ``docker run`` prefix; tests use a plain local command.
    """

    command: tuple[str, ...]
    timeout_seconds: float = 900.0
    """Longest a single compaction may take."""
    max_message_bytes: int = 8 * 1024 * 1024

    @classmethod
    def docker(
        cls,
        image: str,
        *,
        network: str = "none",
        env: Sequence[tuple[str, str]] = (),
        memory: str = "2g",
        cpus: str = "2",
        pids: int = 256,
        timeout_seconds: float = 900.0,
        runtime: str | None = None,
    ) -> Sandbox:
        """A container with no privileges, a read-only filesystem and one network.

        ``runtime="runsc"`` runs it under gVisor, which puts a user-space kernel between
        the method and the host; ranked evaluation uses it because nobody reviews the
        submitted code.
        """
        flags = [
            "docker",
            "run",
            "--rm",
            "-i",
            *(["--runtime", runtime] if runtime else []),
            "--network",
            network,
            "--read-only",
            "--tmpfs",
            "/tmp:rw,size=256m",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--pids-limit",
            str(pids),
            "--memory",
            memory,
            "--cpus",
            cpus,
            "--user",
            "65534:65534",
        ]
        for key, value in env:
            flags += ["-e", f"{key}={value}"]
        return cls(command=(*flags, image), timeout_seconds=timeout_seconds)

    def argv(
        self, method_spec: str, provider_key: str, model: str, config: dict[str, Any]
    ) -> list[str]:
        return [
            *self.command,
            "compactbench",
            "sandbox-serve",
            "--method",
            method_spec,
            "--provider",
            provider_key,
            "--model",
            model,
            "--config",
            json.dumps(config, sort_keys=True),
        ]


# --- inside the sandbox ----------------------------------------------------------------


def serve(method_spec: str, provider_key: str, model: str, config: dict[str, Any]) -> None:
    """Entry point of ``compactbench sandbox-serve``: answer requests until stdin closes."""
    # The protocol owns the original stdout. Anything the method prints goes to
    # stderr instead, and it can't read the protocol's stdin.
    protocol_out = os.fdopen(os.dup(sys.stdout.fileno()), "w", encoding="utf-8")
    protocol_in = os.fdopen(os.dup(sys.stdin.fileno()), "r", encoding="utf-8")
    os.dup2(sys.stderr.fileno(), sys.stdout.fileno())
    devnull = os.open(os.devnull, os.O_RDONLY)
    os.dup2(devnull, sys.stdin.fileno())
    asyncio.run(_serve(method_spec, provider_key, model, config, protocol_in, protocol_out))


async def _serve(
    method_spec: str,
    provider_key: str,
    model: str,
    config: dict[str, Any],
    protocol_in: TextIO,
    protocol_out: TextIO,
) -> None:
    from compactbench.providers import get_provider_cls
    from compactbench.runner._resolver import resolve_compactor_class

    def send(message: dict[str, Any]) -> None:
        protocol_out.write(json.dumps(message) + "\n")
        protocol_out.flush()

    cls = resolve_compactor_class(method_spec)
    counter = CountingProvider(get_provider_cls(provider_key)())
    compactor = cls(counter, model, config)
    send({"type": "hello", "protocol": PROTOCOL, "name": cls.name, "version": cls.version})
    while True:
        line = await asyncio.to_thread(protocol_in.readline)
        if not line:
            return
        try:
            message = json.loads(line)
            if message.get("type") == "close":
                return
            request = CompactionRequest.model_validate(message["request"])
            await counter.reset()
            artifact = await compactor.compact(request)
            usage = await counter.snapshot()
            send(
                {
                    "type": "artifact",
                    "artifact": artifact.model_dump(mode="json", by_alias=True),
                    "usage": usage.model_dump(mode="json"),
                }
            )
        except Exception as exc:  # reported to the harness, which decides
            send({"type": "error", "error": f"{type(exc).__name__}: {exc}"[:2000]})


# --- on the harness side -----------------------------------------------------------------


class _Unused(Provider):
    """Placeholder provider: a sandboxed method makes its own calls, through the proxy."""

    key: ClassVar[str] = "sandboxed"

    async def complete(self, request: CompletionRequest) -> CompletionResponse:  # pragma: no cover
        raise SandboxError("the harness never calls a model for a sandboxed method")


def usage_counter() -> CountingProvider:
    """A counter the harness records the sandbox's reported usage into."""
    return CountingProvider(_Unused())


class SandboxedCompactor(Compactor):
    """A :class:`Compactor` whose work happens in a sandboxed process.

    One process per instance; the runner makes one instance per case and calls
    :meth:`aclose` when the case is done.
    """

    name: ClassVar[str] = "sandboxed"
    version: ClassVar[str] = "0"

    def __init__(
        self,
        sandbox: Sandbox,
        *,
        method_spec: str,
        provider_key: str,
        model: str,
        config: dict[str, Any] | None = None,
        usage: CountingProvider | None = None,
    ) -> None:
        super().__init__(usage or usage_counter(), model, config)
        self.sandbox = sandbox
        self.method_spec = method_spec
        self.provider_key = provider_key
        self.usage = usage
        self.hello: Hello | None = None
        self._process: asyncio.subprocess.Process | None = None
        self._stderr: bytearray = bytearray()
        self._drain: asyncio.Task[None] | None = None

    async def start(self) -> Hello:
        if self.hello is not None:
            return self.hello
        argv = self.sandbox.argv(self.method_spec, self.provider_key, self.model, self.config)
        self._process = await asyncio.create_subprocess_exec(
            *argv,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=self.sandbox.max_message_bytes,
        )
        self._drain = asyncio.create_task(self._drain_stderr())
        message = await self._receive(timeout=120.0)
        if message.get("type") != "hello" or message.get("protocol") != PROTOCOL:
            raise SandboxError(f"sandbox did not say hello: {self._tail()}")
        name, version = str(message.get("name", "")), str(message.get("version", ""))
        if not _NAME.match(name) or not _VERSION.match(version):
            raise SandboxError("sandbox reported an invalid method name or version")
        self.hello = Hello(name=name, version=version)
        return self.hello

    async def compact(self, request: CompactionRequest) -> CompactionArtifact:
        await self.start()
        process = self._process
        assert process is not None
        assert process.stdin is not None
        payload = {"type": "compact", "request": request.model_dump(mode="json", by_alias=True)}
        process.stdin.write((json.dumps(payload) + "\n").encode("utf-8"))
        await process.stdin.drain()
        message = await self._receive(timeout=self.sandbox.timeout_seconds)
        if message.get("type") == "error":
            raise SandboxError(f"method failed: {str(message.get('error'))[:2000]}")
        if message.get("type") != "artifact":
            raise SandboxError("sandbox sent an unexpected message")
        try:
            artifact = CompactionArtifact.model_validate(message.get("artifact"))
            usage = TokenUsage.model_validate(message.get("usage") or {})
        except ValidationError as exc:
            raise SandboxError(f"sandbox sent an invalid artifact: {exc.errors()[:3]}") from exc
        if self.usage is not None:
            await self.usage.record(usage)
        return artifact

    async def _receive(self, *, timeout: float) -> dict[str, Any]:
        process = self._process
        assert process is not None
        assert process.stdout is not None
        try:
            line = await asyncio.wait_for(process.stdout.readline(), timeout=timeout)
        except TimeoutError as exc:
            await self.aclose()
            raise SandboxError(f"sandbox timed out after {timeout:.0f}s") from exc
        except ValueError as exc:  # line longer than the stream limit
            await self.aclose()
            raise SandboxError("sandbox message too large") from exc
        if not line:
            raise SandboxError(f"sandbox exited: {self._tail()}")
        try:
            message = json.loads(line)
        except ValueError as exc:
            raise SandboxError("sandbox broke the protocol (not JSON)") from exc
        if not isinstance(message, dict):
            raise SandboxError("sandbox broke the protocol (not an object)")
        return message  # pyright: ignore[reportUnknownVariableType]

    async def _drain_stderr(self) -> None:
        process = self._process
        assert process is not None
        assert process.stderr is not None
        while chunk := await process.stderr.read(65536):
            self._stderr += chunk
            del self._stderr[:-65536]

    def _tail(self) -> str:
        return self._stderr.decode("utf-8", "replace")[-1500:].strip() or "(no output)"

    async def aclose(self) -> None:
        process = self._process
        if process is None:
            return
        self._process = None
        if process.stdin is not None and not process.stdin.is_closing():
            process.stdin.close()
        try:
            await asyncio.wait_for(process.wait(), timeout=10)
        except TimeoutError:
            with contextlib.suppress(ProcessLookupError):
                process.kill()
            await process.wait()
        if self._drain is not None:
            self._drain.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._drain
