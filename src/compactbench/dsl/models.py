"""Pydantic models for parsed template definitions.

These are distinct from ``compactbench.contracts.case`` — template models carry
``{{placeholder}}`` strings; contract models carry realized values produced by
the engine at generation time.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DifficultyLevel(StrEnum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"
    ELITE = "elite"


class TemplateTurnRole(StrEnum):
    """Roles permitted in a template turn.

    ``distractor_block`` is a template-only pseudo-role that the engine expands
    to multiple concrete turns at generation time.
    """

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    DISTRACTOR_BLOCK = "distractor_block"


class VariableDeclaration(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, pattern=r"^[a-zA-Z_]\w*$")
    generator: str = Field(min_length=1)


class DifficultyPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    distractor_turns: dict[DifficultyLevel, int] = Field(default_factory=dict[DifficultyLevel, int])
    paraphrase_depth: dict[DifficultyLevel, int] = Field(default_factory=dict[DifficultyLevel, int])
    override_timing: dict[DifficultyLevel, str] = Field(default_factory=dict[DifficultyLevel, str])


class TurnTemplate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    role: TemplateTurnRole
    template: str | None = None
    tags: list[str] = Field(default_factory=list[str])
    count: str | int | None = None

    @model_validator(mode="after")
    def _check_role_requirements(self) -> TurnTemplate:
        text_roles = {TemplateTurnRole.USER, TemplateTurnRole.ASSISTANT, TemplateTurnRole.SYSTEM}
        if self.role in text_roles and not self.template:
            raise ValueError(f"role {self.role.value!r} requires a non-empty 'template'")
        if self.role is TemplateTurnRole.DISTRACTOR_BLOCK and self.count is None:
            raise ValueError("role 'distractor_block' requires 'count'")
        return self


class TranscriptTemplate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    turns: list[TurnTemplate]


class GroundTruthTemplate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    immutable_facts: list[str] = Field(default_factory=list[str])
    locked_decisions: list[str] = Field(default_factory=list[str])
    forbidden_behaviors: list[str] = Field(default_factory=list[str])
    unresolved_items: list[str] = Field(default_factory=list[str])
    deferred_items: list[str] = Field(default_factory=list[str])
    entity_map: dict[str, str] = Field(default_factory=dict[str, str])


class EvaluationItemTemplate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str = Field(min_length=1, pattern=r"^[a-zA-Z_]\w*$")
    type: str = Field(min_length=1)
    prompt: str = Field(min_length=1)
    expected: dict[str, Any]


class TemplateDefinition(BaseModel):
    """A parsed template before variable resolution or difficulty application."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str = Field(min_length=1, pattern=r"^[a-zA-Z_][\w-]*$")
    family: str = Field(min_length=1, pattern=r"^[a-zA-Z_]\w*$")
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    difficulty_policy: DifficultyPolicy
    variables: list[VariableDeclaration] = Field(default_factory=list[VariableDeclaration])
    transcript: TranscriptTemplate
    ground_truth: GroundTruthTemplate
    evaluation_items: list[EvaluationItemTemplate]
