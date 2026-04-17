"""Scoring-specific exceptions."""

from __future__ import annotations


class ScoringError(Exception):
    """Raised when scoring inputs are malformed or a check cannot run."""
