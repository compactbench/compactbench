"""Leaderboard-specific exceptions."""

from __future__ import annotations


class LeaderboardError(Exception):
    """Base exception for leaderboard operations."""


class QualificationError(LeaderboardError):
    """Raised (or returned as a failure reason) when a run fails qualification floors."""
