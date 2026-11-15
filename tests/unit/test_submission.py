"""The ranked submission bundle."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from compactbench.submission import SubmissionBundle

pytestmark = pytest.mark.unit

SEALED = "cbseal1:" + "A" * 120


def _bundle(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
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
        "requirements": "tiktoken==0.12.0\n# comment\npydantic[email]==2.11.0\n",
        "sealed_method_key": SEALED,
        "sealed_reader_key": SEALED,
        "created_at": "2026-11-01T00:00:00Z",
    }
    base.update(overrides)
    return base


def test_valid_bundle_and_public_view() -> None:
    bundle = SubmissionBundle.model_validate(_bundle())
    assert bundle.submission == "alice/ledger"
    public = bundle.public()
    assert "sealed_method_key" not in public
    assert "sealed_reader_key" not in public


def test_anthropic_method_can_reuse_its_key_for_the_reader() -> None:
    SubmissionBundle.model_validate(_bundle(provider="anthropic", sealed_reader_key=None))


def test_custom_endpoint_needs_https_and_may_skip_the_method_key() -> None:
    SubmissionBundle.model_validate(
        _bundle(provider="custom", base_url="https://models.example.com/v1", sealed_method_key=None)
    )
    with pytest.raises(ValidationError):
        SubmissionBundle.model_validate(_bundle(provider="custom", base_url="http://x.example/v1"))


@pytest.mark.parametrize(
    "overrides",
    [
        {"sealed_reader_key": None},  # non-Anthropic method without a reader key
        {"sealed_method_key": None},  # hosted provider without its key
        {"provider": "ollama"},  # no ranked route
        {"base_url": "https://x.example/v1"},  # base_url outside 'custom'
        {"requirements": "torch>=2.0\n"},  # not pinned
        {"requirements": "git+https://evil.example/pkg.git\n"},  # URL
        {"requirements": "--index-url https://evil.example\n"},  # pip option
        {"method_py": "x" * 200_001},
        {"handle": "-bad-"},
        {"model": "llama 3"},  # whitespace
        {"sealed_method_key": "sk-plain-key"},  # a plain key would be a leak
        {"extra": "field"},
    ],
)
def test_rejects_malformed_bundles(overrides: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        SubmissionBundle.model_validate(_bundle(**overrides))


def test_custom_models_can_have_a_display_name_hosted_ones_cannot() -> None:
    bundle = SubmissionBundle.model_validate(
        _bundle(
            provider="custom",
            base_url="https://models.example.com/v1",
            model="ft-7b-0423",
            model_label="Acme Recall v2 (7B)",
        )
    )
    assert bundle.model_label == "Acme Recall v2 (7B)"
    with pytest.raises(ValidationError):
        SubmissionBundle.model_validate(_bundle(model_label="GPT-9"))
    with pytest.raises(ValidationError):
        SubmissionBundle.model_validate(
            _bundle(provider="custom", base_url="https://m.example/v1", model_label="<script>")
        )


def _reference(**overrides: Any) -> dict[str, Any]:
    fields = _bundle(
        reference_method="sectioned-summary",
        method_name="sectioned-summary",
        method_version="1.0.0",
        class_name=None,
        method_py="",
        requirements="",
    )
    fields.update(overrides)
    return fields


def test_a_reference_method_runs_a_built_in_on_the_submitters_model() -> None:
    bundle = SubmissionBundle.model_validate(_reference())
    assert bundle.method_spec == "built-in:sectioned-summary"
    assert bundle.submission == "alice/sectioned-summary--openrouter--qwen-qwen3-235b"
    assert bundle.public()["reference_method"] == "sectioned-summary"


def test_an_uploaded_method_runs_from_the_image() -> None:
    bundle = SubmissionBundle.model_validate(_bundle())
    assert bundle.method_spec == "/opt/submission/method.py:Ledger"
    assert bundle.reference_method is None


def test_a_custom_models_display_name_names_its_directory() -> None:
    bundle = SubmissionBundle.model_validate(
        _reference(
            provider="custom",
            base_url="https://models.example.com/v1",
            sealed_method_key=None,
            model="ft:abc123",
            model_label="Acme Mini (2026)",
        )
    )
    assert bundle.submission == "alice/sectioned-summary--custom--acme-mini-2026"


@pytest.mark.parametrize(
    "overrides",
    [
        {"reference_method": "ledger"},
        {"method_py": "class X: ...\n"},
        {"requirements": "tiktoken==0.12.0\n"},
        {"class_name": "X"},
        {"method_config": {"reasoning_effort": "high"}},
        {"method_name": "my-summary"},
        {"method_version": "9.9.9"},
    ],
)
def test_a_reference_method_submission_is_only_the_method_and_model(
    overrides: dict[str, Any],
) -> None:
    with pytest.raises(ValidationError):
        SubmissionBundle.model_validate(_reference(**overrides))


def test_an_uploaded_method_needs_code_and_a_class() -> None:
    with pytest.raises(ValidationError, match=r"method\.py is empty"):
        SubmissionBundle.model_validate(_bundle(method_py="  \n"))
    with pytest.raises(ValidationError, match="class_name is required"):
        SubmissionBundle.model_validate(_bundle(class_name=None))


def test_reference_versions_match_the_built_ins() -> None:
    from compactbench.compactors import get_built_in
    from compactbench.submission import REFERENCE_METHODS

    for key, version in REFERENCE_METHODS.items():
        assert get_built_in(key).version == version
