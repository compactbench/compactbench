"""Runner-specific exceptions."""

from __future__ import annotations


class RunnerError(Exception):
    """Base exception for runner operations."""


class ResumeError(RunnerError):
    """Resume requested but the existing results file is incompatible."""


class MethodResolutionError(RunnerError):
    """The ``--method`` spec could not be resolved to a Compactor class."""
