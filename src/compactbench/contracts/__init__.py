"""Canonical data contracts shared across the engine, scorer, and providers."""

from compactbench.contracts.artifact import (
    ARTIFACT_SCHEMA_VERSION,
    CompactionArtifact,
    StructuredState,
)
from compactbench.contracts.case import (
    EvaluationItem,
    EvaluationItemType,
    GeneratedCase,
    GroundTruth,
    Transcript,
    Turn,
    TurnRole,
)
from compactbench.contracts.result import (
    CaseResult,
    CycleResult,
    ItemScore,
    RunResult,
    Scorecard,
    TokenUsage,
)

__all__ = [
    "ARTIFACT_SCHEMA_VERSION",
    "CaseResult",
    "CompactionArtifact",
    "CycleResult",
    "EvaluationItem",
    "EvaluationItemType",
    "GeneratedCase",
    "GroundTruth",
    "ItemScore",
    "RunResult",
    "Scorecard",
    "StructuredState",
    "TokenUsage",
    "Transcript",
    "Turn",
    "TurnRole",
]
