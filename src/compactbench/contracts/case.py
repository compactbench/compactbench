"""Generated-case contract: transcript, ground truth, and evaluation items."""

from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TurnRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class Turn(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: int = Field(ge=0)
    role: TurnRole
    content: str
    tags: list[str] = Field(default_factory=list)


class Transcript(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    turns: list[Turn]

    def chars_by_role(self) -> dict[TurnRole, int]:
        """Total character count of turn content, grouped by role.

        Cheap O(n) helper that requires no tokenizer. Use :meth:`tokens_by_role`
        when you actually need token counts.
        """
        return {
            role: sum(len(t.content) for t in self.turns if t.role == role) for role in TurnRole
        }

    def tokens_by_role(self, tokenize: Callable[[str], int]) -> dict[TurnRole, int]:
        """Total token count of turn content, grouped by role.

        ``tokenize`` is a callable ``(text: str) -> int`` returning the token
        count for a given string. Typically ``lambda s: len(encoding.encode(s))``
        with a ``tiktoken`` encoding; any equivalent counter works.
        """
        return {
            role: sum(tokenize(t.content) for t in self.turns if t.role == role)
            for role in TurnRole
        }


class GroundTruth(BaseModel):
    """What the compactor must preserve for the case to score well."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    immutable_facts: list[str] = Field(default_factory=list)
    locked_decisions: list[str] = Field(default_factory=list)
    forbidden_behaviors: list[str] = Field(default_factory=list)
    unresolved_items: list[str] = Field(default_factory=list)
    deferred_items: list[str] = Field(default_factory=list)
    entity_map: dict[str, str] = Field(default_factory=dict)


class EvaluationItemType(StrEnum):
    LOCKED_DECISION_RETENTION = "locked_decision_retention"
    FORBIDDEN_BEHAVIOR_RETENTION = "forbidden_behavior_retention"
    IMMUTABLE_FACT_RECALL = "immutable_fact_recall"
    UNRESOLVED_TASK_CONTINUITY = "unresolved_task_continuity"
    ENTITY_INTEGRITY = "entity_integrity"
    PLANNING_SOUNDNESS = "planning_soundness"


class EvaluationItem(BaseModel):
    """A single scorer question bound to a case."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str
    item_type: EvaluationItemType
    prompt: str
    expected: dict[str, Any]


class GeneratedCase(BaseModel):
    """A concrete benchmark case produced by the engine for a given seed."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str
    template_key: str
    template_version: str
    seed: int
    difficulty: str
    transcript: Transcript
    ground_truth: GroundTruth
    evaluation_items: list[EvaluationItem]
