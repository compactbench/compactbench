"""Provider-specific exceptions."""

from __future__ import annotations


class ProviderError(Exception):
    """Base exception for provider operations."""


class UnknownProviderError(ProviderError):
    """Requested provider key is not registered."""


class ProviderResponseError(ProviderError):
    """Provider returned a malformed or unusable response."""
