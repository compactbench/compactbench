"""Canonical data contracts shared across the engine, scorer, and providers."""

from compactbench.contracts.artifact import (
    ARTIFACT_SCHEMA_VERSION,
    CompactionArtifact,
    StructuredState,
)
from compactbench.contracts.case import (
    NOT_STATED,
    CycleSpec,
    GeneratedCase,
    Probe,
    ProbeCategory,
    ProbeFormat,
    Transcript,
    Turn,
    TurnRole,
    ValueKind,
)
from compactbench.contracts.request import CompactionRequest
from compactbench.contracts.result import (
    CaseResult,
    CategoryMetrics,
    CycleResult,
    FamilyMetrics,
    ProbeResult,
    RunMetrics,
    RunResult,
    TokenUsage,
    add_usage,
)

__all__ = [
    "ARTIFACT_SCHEMA_VERSION",
    "NOT_STATED",
    "CaseResult",
    "CategoryMetrics",
    "CompactionArtifact",
    "CompactionRequest",
    "CycleResult",
    "CycleSpec",
    "FamilyMetrics",
    "GeneratedCase",
    "Probe",
    "ProbeCategory",
    "ProbeFormat",
    "ProbeResult",
    "RunMetrics",
    "RunResult",
    "StructuredState",
    "TokenUsage",
    "Transcript",
    "Turn",
    "TurnRole",
    "ValueKind",
    "add_usage",
]
