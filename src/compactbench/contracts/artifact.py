"""Compaction artifact contract.

Mirrors the JSON Schema locked in docs/architecture/decisions.md §B2.
Every built-in and external compactor must return an instance of
``CompactionArtifact`` that validates against this shape.
"""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

ARTIFACT_SCHEMA_VERSION = "1.0.0"

_Bounded = Annotated[str, StringConstraints(min_length=1, max_length=500)]


class StructuredState(BaseModel):
    """Six required sections that every compaction artifact must carry.

    Empty arrays / empty object are allowed. Missing keys are not.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    immutable_facts: list[_Bounded] = Field(default_factory=list, max_length=200)
    locked_decisions: list[_Bounded] = Field(default_factory=list, max_length=200)
    deferred_items: list[_Bounded] = Field(default_factory=list, max_length=200)
    forbidden_behaviors: list[_Bounded] = Field(default_factory=list, max_length=200)
    entity_map: dict[str, _Bounded] = Field(default_factory=dict)
    unresolved_items: list[_Bounded] = Field(default_factory=list, max_length=200)


class CompactionArtifact(BaseModel):
    """Canonical artifact returned by a compactor for a single compaction step."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = Field(default=ARTIFACT_SCHEMA_VERSION, alias="schemaVersion")
    summary_text: Annotated[str, StringConstraints(max_length=8000)] = Field(
        default="", alias="summaryText"
    )
    structured_state: StructuredState = Field(default_factory=StructuredState)
    selected_source_turn_ids: list[int] = Field(
        default_factory=list[int], alias="selectedSourceTurnIds"
    )
    warnings: list[_Bounded] = Field(default_factory=list, max_length=50)
    method_metadata: dict[str, Any] = Field(default_factory=dict, alias="methodMetadata")
