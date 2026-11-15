"""Ranked submissions: the bundle the website builds and the evaluation consumes.

A submission is made on the website by a submitter signed in with GitHub. The site
validates it, seals the submitter's API keys to the season's public key, and stores
a :class:`SubmissionBundle`. The evaluation workflow fetches the bundle, validates it
again here, builds the method into a sandbox image and runs it. Nobody reviews the
code by hand: the sandbox is the safety boundary, and these checks keep the inputs
well-formed.

Keys: the method's key pays for the method's own model calls and is opened only
inside the model proxy. The reader key pays for grading and is opened only by the
harness. A method on Anthropic can use one key for both.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

#: Providers a ranked method may call: each has a route in the model proxy.
#: ``custom`` is the submitter's own OpenAI-compatible endpoint (``base_url``).
RankedProvider = Literal[
    "anthropic",
    "openai",
    "groq",
    "openrouter",
    "deepseek",
    "mistral",
    "together",
    "fireworks",
    "xai",
    "gemini",
    "custom",
]

MAX_METHOD_BYTES = 200_000
MAX_REQUIREMENTS_BYTES = 4_000
MAX_CONFIG_BYTES = 16_384
_SEALED = r"^cbseal1:[A-Za-z0-9_-]{80,4096}$"
# One pinned requirement per line: name, optional extras, an exact version. No URLs,
# paths, or pip options, so a build only ever installs named releases from PyPI.
_REQUIREMENT = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._-]*(\[[A-Za-z0-9,._-]+\])?==[A-Za-z0-9][A-Za-z0-9.+!_-]*$"
)


def method_key_context(season: str, submission_id: str) -> str:
    return f"key:{season}:{submission_id}"


def reader_key_context(season: str, submission_id: str) -> str:
    return f"reader:{season}:{submission_id}"


class SubmissionBundle(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=r"^[a-z0-9]{12,32}$")
    season: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,31}$")
    handle: str = Field(pattern=r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")
    github_id: int = Field(ge=1)
    method_name: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{0,63}$")
    method_version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    class_name: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
    provider: RankedProvider
    model: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/@-]{0,127}$")
    base_url: str | None = None
    model_label: str | None = Field(default=None, pattern=r"^[A-Za-z0-9][A-Za-z0-9 ._+()/-]{0,47}$")
    """Display name for a custom endpoint's model, shown instead of ``model``."""
    method_config: dict[str, Any] = Field(default_factory=dict)
    method_py: str = Field(min_length=1)
    requirements: str = ""
    sealed_method_key: str | None = Field(default=None, pattern=_SEALED)
    sealed_reader_key: str | None = Field(default=None, pattern=_SEALED)
    created_at: str

    @field_validator("method_py")
    @classmethod
    def _method_size(cls, value: str) -> str:
        if len(value.encode("utf-8")) > MAX_METHOD_BYTES:
            raise ValueError(f"method.py is larger than {MAX_METHOD_BYTES} bytes")
        if "\x00" in value:
            raise ValueError("method.py contains a NUL byte")
        return value

    @field_validator("requirements")
    @classmethod
    def _requirements(cls, value: str) -> str:
        if len(value.encode("utf-8")) > MAX_REQUIREMENTS_BYTES:
            raise ValueError(f"requirements are larger than {MAX_REQUIREMENTS_BYTES} bytes")
        for line in value.splitlines():
            line = line.strip()
            if line and not line.startswith("#") and not _REQUIREMENT.match(line):
                raise ValueError(
                    f"requirement {line[:80]!r} must be pinned as name==version "
                    "(no URLs, paths or pip options)"
                )
        return value

    @field_validator("method_config")
    @classmethod
    def _config_size(cls, value: dict[str, Any]) -> dict[str, Any]:
        if len(json.dumps(value).encode("utf-8")) > MAX_CONFIG_BYTES:
            raise ValueError(f"method_config is larger than {MAX_CONFIG_BYTES} bytes")
        return value

    @model_validator(mode="after")
    def _keys_and_endpoint(self) -> Self:
        if self.model_label is not None and self.provider != "custom":
            raise ValueError(
                "model_label is only for provider 'custom'; hosted models keep their id"
            )
        if self.provider == "custom":
            if not self.base_url or not self.base_url.startswith("https://"):
                raise ValueError("provider 'custom' needs an https:// base_url")
        elif self.base_url is not None:
            raise ValueError("base_url is only for provider 'custom'")
        elif self.sealed_method_key is None:
            raise ValueError(f"provider {self.provider!r} needs a sealed method key")
        if self.sealed_reader_key is None and self.provider != "anthropic":
            raise ValueError("a sealed Anthropic key for the reader is required")
        return self

    @property
    def submission(self) -> str:
        """``<handle>/<method>``: where the published submission lives in the repo."""
        return f"{self.handle}/{self.method_name}"

    def public(self) -> dict[str, Any]:
        """What is published with the results: everything except the sealed keys."""
        return self.model_dump(exclude={"sealed_method_key", "sealed_reader_key", "method_py"})


def load_bundle(path: Path) -> SubmissionBundle:
    return SubmissionBundle.model_validate_json(path.read_text(encoding="utf-8"))


def main(argv: list[str]) -> int:
    """``python -m compactbench.submission validate bundle.json``"""
    if len(argv) != 3 or argv[1] != "validate":
        print("usage: python -m compactbench.submission validate <bundle.json>", file=sys.stderr)
        return 2
    try:
        bundle = load_bundle(Path(argv[2]))
    except (OSError, ValueError) as exc:
        print(f"::error::invalid submission bundle: {str(exc)[:2000]}")
        return 1
    print(f"ok: {bundle.submission} {bundle.method_version} ({bundle.provider}/{bundle.model})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
