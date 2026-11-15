"""Run one ranked evaluation: proxy up, sandboxed run, proxy down, traces sealed.

    python scripts/ranked/evaluate.py --bundle bundle.json --image IMAGE \
        --proxy-image PROXY_IMAGE --season seasons/s1.yaml --suite-pack PACK --out DIR \
        [--runtime runsc]

Called by the ``evaluate`` job after the submission image is built. The submission
arrives as a website bundle (``compactbench.submission.SubmissionBundle``), validated
again here, and every value from it is passed as a single argument to a subprocess —
never through a shell or an environment file.

Keys:

- The method's sealed key is opened inside the proxy container only, which gets the
  season's private key for that purpose. The sandbox never sees a key.
- The reader's sealed key (the submitter's Anthropic key) is opened here and given
  to the harness process only, which uses it to grade. A method on Anthropic without
  a separate reader key uses its own key for both.

Environment (secrets, set only on this step):

- ``COMPACTBENCH_SEASON_PRIVATE_KEY`` — opens the sealed keys; removed from this
  process's environment once used.
- ``COMPACTBENCH_TRACE_PUBLIC_KEY`` — maintainers' key the traces are sealed to.

Writes ``results.jsonl`` (scores only, redacted — see ``compactbench.redaction`` — and
safe to publish), ``results.sealed`` (the unredacted results), ``traces.sealed``,
``calls.sealed`` and ``commitment.json`` to ``--out``. Nothing else from the run
leaves its private working directory.
"""

from __future__ import annotations

import argparse
import atexit
import hashlib
import json
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

# Provider → (proxy route, environment the sandbox's SDK needs). The SDKs read these
# variables themselves; the API key is a placeholder the proxy replaces.
SANDBOX_ROUTES: dict[str, tuple[str, dict[str, str]]] = {
    "anthropic": (
        "anthropic",
        {
            "ANTHROPIC_BASE_URL": "http://{proxy}:8080/anthropic",
            "COMPACTBENCH_ANTHROPIC_API_KEY": "sandbox",
        },
    ),
    "openai": (
        "openai",
        {
            "OPENAI_BASE_URL": "http://{proxy}:8080/openai/v1",
            "COMPACTBENCH_OPENAI_API_KEY": "sandbox",
        },
    ),
    "groq": (
        "groq",
        {"GROQ_BASE_URL": "http://{proxy}:8080/groq", "COMPACTBENCH_GROQ_API_KEY": "sandbox"},
    ),
    # Hosted OpenAI-compatible APIs: the provider's own base-URL override, pointed at
    # the proxy route plus the host's API path.
    **{
        name: (
            name,
            {
                f"COMPACTBENCH_{name.upper()}_BASE_URL": f"http://{{proxy}}:8080/{name}{path}",
                f"COMPACTBENCH_{name.upper()}_API_KEY": "sandbox",
            },
        )
        for name, path in (
            ("openrouter", "/api/v1"),
            ("deepseek", "/v1"),
            ("mistral", "/v1"),
            ("together", "/v1"),
            ("fireworks", "/inference/v1"),
            ("xai", "/v1"),
            ("gemini", "/v1beta/openai"),
        )
    },
}
DEFAULT_MAX_TOKENS = 40_000_000


def sandbox_setup(
    provider: str, base_url: str | None, proxy: str
) -> tuple[str, str, dict[str, str], str]:
    """``(compactbench provider, proxy route, sandbox env, endpoint kind)`` for a method.

    A ``custom`` endpoint goes through the proxy's ``custom`` route with the OpenAI
    client, and is recorded as a custom endpoint.
    """
    if provider == "custom":
        path = urlsplit(base_url or "").path.rstrip("/")
        env = {
            "COMPACTBENCH_OPENAI_BASE_URL": f"http://{proxy}:8080/custom{path}",
            "COMPACTBENCH_OPENAI_API_KEY": "sandbox",
        }
        return "openai", "custom", env, "custom"
    route, env = SANDBOX_ROUTES[provider]
    return provider, route, {k: v.format(proxy=proxy) for k, v in env.items()}, "default"


def _run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, check=True, text=True, **kwargs)


def _wait_for_proxy(name: str, timeout: float = 60.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        logs = subprocess.run(["docker", "logs", name], capture_output=True, text=True, check=False)
        if "proxy listening" in logs.stdout + logs.stderr:
            return
        time.sleep(1)
    raise RuntimeError("proxy did not start")


def _seal(public_key: str, source: Path, target: Path, context: str) -> str:
    from compactbench.sealing import seal

    data = source.read_bytes() if source.exists() else b""
    target.write_text(seal(public_key, data, context=context), encoding="ascii")
    return "sha256:" + hashlib.sha256(data).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--proxy-image", required=True)
    parser.add_argument("--season", type=Path, required=True)
    parser.add_argument("--suite-pack", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    parser.add_argument("--runtime", default=None, help="Sandbox container runtime (runsc).")
    args = parser.parse_args()

    from compactbench.leaderboard import load_season
    from compactbench.sealing import SealingError, open_sealed
    from compactbench.submission import load_bundle, method_key_context, reader_key_context

    bundle = load_bundle(args.bundle)
    season = load_season(args.season)
    if bundle.season != season.key:
        print(f"::error::bundle is for season {bundle.season!r}, not {season.key!r}")
        return 1

    private_key = os.environ.pop("COMPACTBENCH_SEASON_PRIVATE_KEY", "")
    trace_key = os.environ.get("COMPACTBENCH_TRACE_PUBLIC_KEY", "")
    if not private_key or not trace_key:
        print("::error::season private key or trace public key is missing")
        return 1

    # The reader key never enters a container: the harness grades with it.
    try:
        if bundle.sealed_reader_key:
            reader_key = open_sealed(
                private_key,
                bundle.sealed_reader_key,
                context=reader_key_context(season.key, bundle.id),
            )
        else:
            assert bundle.sealed_method_key is not None  # anthropic, checked by the bundle
            reader_key = open_sealed(
                private_key,
                bundle.sealed_method_key,
                context=method_key_context(season.key, bundle.id),
            )
    except SealingError:
        print("::error::the reader key doesn't open for this submission")
        return 1
    # The harness gets the reader key and nothing else of ours.
    harness_env = {k: v for k, v in os.environ.items() if not k.startswith("COMPACTBENCH_")}
    harness_env["COMPACTBENCH_ANTHROPIC_API_KEY"] = reader_key.decode("utf-8")
    del reader_key

    tag = secrets.token_hex(4)
    network, proxy = f"cb-sandbox-{tag}", f"cb-proxy-{tag}"
    provider, route, sdk_env, endpoint_kind = sandbox_setup(bundle.provider, bundle.base_url, proxy)
    args.out.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="cb-eval-"))
    # Plaintext traces, raw results and the sealed key live here: gone however we exit.
    atexit.register(shutil.rmtree, work, ignore_errors=True)
    logs = work / "proxy-logs"
    logs.mkdir()
    logs.chmod(0o777)

    proxy_argv = [
        "docker",
        "run",
        "-d",
        "--name",
        proxy,
        "--network",
        "bridge",
        "-v",
        f"{logs}:/log",
    ]
    proxy_args = [
        "--route",
        route,
        "--allow-model",
        bundle.model,
        "--max-tokens",
        str(args.max_tokens),
        "--log",
        "/log/calls.jsonl",
    ]
    proxy_env = dict(os.environ)
    if bundle.sealed_method_key:
        sealed_file = work / "sealed-key"
        sealed_file.write_text(bundle.sealed_method_key, encoding="ascii")
        sealed_file.chmod(0o644)  # read by the proxy's unprivileged user
        proxy_argv += [
            "-e",
            "COMPACTBENCH_SEASON_PRIVATE_KEY",
            "-v",
            f"{sealed_file}:/run/sealed-key:ro",
        ]
        proxy_args += [
            "--sealed-key",
            "/run/sealed-key",
            "--context",
            method_key_context(season.key, bundle.id),
        ]
        proxy_env["COMPACTBENCH_SEASON_PRIVATE_KEY"] = private_key
    else:
        # A custom endpoint that needs no key.
        proxy_args.append("--no-key")
    if bundle.base_url:
        proxy_args += ["--upstream", bundle.base_url]
    del private_key

    try:
        _run(["docker", "network", "create", "--internal", network], capture_output=True)
        _run([*proxy_argv, args.proxy_image, *proxy_args], capture_output=True, env=proxy_env)
        del proxy_env
        _run(["docker", "network", "connect", network, proxy], capture_output=True)
        _wait_for_proxy(proxy)

        argv = [
            sys.executable,
            "-m",
            "compactbench",
            "run",
            "--season",
            str(args.season),
            "--suite-pack",
            str(args.suite_pack),
            "--method",
            bundle.method_spec,
            "--provider",
            provider,
            "--model",
            bundle.model,
            "--method-config",
            json.dumps(bundle.method_config),
            "--sandbox-image",
            args.image,
            "--sandbox-network",
            network,
            "--sandbox-endpoint-kind",
            endpoint_kind,
            "--method-name",
            bundle.method_name,
            "--method-version",
            bundle.method_version,
            "--traces",
            str(work / "traces.jsonl"),
            "--output",
            str(work / "results.raw.jsonl"),
            "--concurrency",
            "3",
        ]
        if args.runtime:
            argv += ["--sandbox-runtime", args.runtime]
        for key, value in sdk_env.items():
            argv += ["--sandbox-env", f"{key}={value}"]
        _run(argv, env=harness_env)
    finally:
        subprocess.run(["docker", "rm", "-f", proxy], capture_output=True, check=False)
        subprocess.run(["docker", "network", "rm", network], capture_output=True, check=False)

    from compactbench.redaction import redact_results

    redact_results(work / "results.raw.jsonl", args.out / "results.jsonl")
    commitment = {
        "results_sha256": "sha256:"
        + hashlib.sha256((args.out / "results.jsonl").read_bytes()).hexdigest(),
        "raw_results_sha256": _seal(
            trace_key, work / "results.raw.jsonl", args.out / "results.sealed", "results:" + tag
        ),
        "traces_sha256": _seal(
            trace_key, work / "traces.jsonl", args.out / "traces.sealed", "traces:" + tag
        ),
        "calls_sha256": _seal(
            trace_key, logs / "calls.jsonl", args.out / "calls.sealed", "calls:" + tag
        ),
        "seal_context_tag": tag,
        "submission_id": bundle.id,
        "submission": bundle.submission,
    }
    (args.out / "commitment.json").write_text(json.dumps(commitment, indent=2), encoding="utf-8")
    (args.out / "submission.json").write_text(
        json.dumps(bundle.public(), indent=2), encoding="utf-8"
    )
    print(json.dumps(commitment))
    return 0


if __name__ == "__main__":
    sys.exit(main())
