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
