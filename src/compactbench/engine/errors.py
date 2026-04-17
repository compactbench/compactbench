"""Exceptions raised by the case generation engine."""

from __future__ import annotations


class EngineError(Exception):
    """Base exception for anything engine-related."""


class GenerationError(EngineError):
    """Case generation failed (unsupported expression, missing config, etc.)."""
