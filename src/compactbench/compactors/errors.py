"""Compactor-specific exceptions."""

from __future__ import annotations


class CompactorError(Exception):
    """Base exception for compactor operations."""


class UnknownCompactorError(CompactorError):
    """Requested built-in compactor key is not registered."""
