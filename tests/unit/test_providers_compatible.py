"""Hosted OpenAI-compatible providers."""

from __future__ import annotations

from urllib.parse import urlsplit

import pytest

from compactbench.providers import get_provider_cls, list_providers
from compactbench.providers.compatible import (
    HOSTED_PROVIDERS,
    HostedCompatibleProvider,
    OpenRouterProvider,
)
from compactbench.providers.errors import ProviderError
from compactbench.proxy import ROUTES

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("cls", HOSTED_PROVIDERS)
def test_registered_with_a_proxy_route(cls: type[HostedCompatibleProvider]) -> None:
    assert cls.key in list_providers()
    assert get_provider_cls(cls.key) is cls
    # Ranked runs reach the host only through the proxy, so every host needs a route
    # that allows the chat endpoint under the provider's default base URL.
    path = urlsplit(cls.default_base_url).path.rstrip("/")
    assert ROUTES[cls.key].allows(f"{path}/chat/completions")


def test_requires_its_own_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("COMPACTBENCH_OPENROUTER_API_KEY", raising=False)
    with pytest.raises(ProviderError, match="COMPACTBENCH_OPENROUTER_API_KEY"):
        OpenRouterProvider()


def test_default_endpoint_and_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COMPACTBENCH_OPENROUTER_API_KEY", "k")
    monkeypatch.delenv("COMPACTBENCH_OPENROUTER_BASE_URL", raising=False)
    assert OpenRouterProvider().endpoint_kind == "default"
    monkeypatch.setenv("COMPACTBENCH_OPENROUTER_BASE_URL", "http://proxy:8080/openrouter/api/v1")
    assert OpenRouterProvider().endpoint_kind == "custom"


def test_effort_is_translated_per_host(monkeypatch: pytest.MonkeyPatch) -> None:
    for cls in HOSTED_PROVIDERS:
        monkeypatch.setenv(f"COMPACTBENCH_{cls.env_name}_API_KEY", "k")
    effort = {cls.key: cls()._effort_kwargs("low") for cls in HOSTED_PROVIDERS}  # pyright: ignore[reportPrivateUsage]
    assert effort["openrouter"] == {"extra_body": {"reasoning": {"effort": "low"}}}
    assert effort["xai"] == {"reasoning_effort": "low"}
    assert effort["deepseek"] == {}
