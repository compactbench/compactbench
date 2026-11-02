"""Generated-case contract: conversation segments and the probes asked after each compaction.

A v2 case is a sequence of **cycles**. Cycle 0 holds the opening conversation;
every later cycle holds only the turns that happened *after* the previous
compaction. After compacting cycle ``k`` the reader answers that cycle's
probes using nothing but the compacted artifact.

Probes are structured so every answer is checked mechanically: single choice,
select-all-that-apply, an exact value, or a list of values. Wrong options are
built from the case itself (superseded decisions, rules that apply to a
different project, look-alike people), so a lossy summary picks them.
"""

from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

NOT_STATED = "Not stated in the conversation"
"""Option text (and value sentinel) meaning the conversation never settled this."""


class TurnRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class Turn(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: int = Field(ge=0)
    role: TurnRole
    content: str
    name: str | None = Field(
        default=None, description="Tool name for TOOL turns; unused for other roles."
    )
    tags: list[str] = Field(default_factory=list)


class Transcript(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    turns: list[Turn]

    def without_tags(self) -> Transcript:
        """Return a copy with every turn's ``tags`` cleared.

        ``tags`` are generation metadata — ``distractor`` marks filler turns and
        e.g. ``critical_constraint`` marks the turn holding the answer. Handing
        them to a compaction method is handing it the answer key: a five-line
        method with no model call that simply drops ``distractor``-tagged turns
        recovers 100% of the recall items at ~9x compression, which would top
        the leaderboard while doing nothing a real compactor does.

        The runner calls this immediately before invoking a method, so no
        compactor — built-in, submitted, or reached through the LangChain and
        LlamaIndex adapters — can see them. Tags stay on the generated case for
        diagnostics and fixtures, which is where they are actually useful.
        """
        return Transcript(turns=[t.model_copy(update={"tags": []}) for t in self.turns])

    def chars_by_role(self) -> dict[TurnRole, int]:
        """Total character count of turn content, grouped by role."""
        return {
            role: sum(len(t.content) for t in self.turns if t.role == role) for role in TurnRole
        }

    def tokens_by_role(self, tokenize: Callable[[str], int]) -> dict[TurnRole, int]:
        """Total token count of turn content, grouped by role.

        ``tokenize`` is a callable ``(text: str) -> int`` returning the token
        count for a given string.
        """
        return {
            role: sum(tokenize(t.content) for t in self.turns if t.role == role)
            for role in TurnRole
        }


class ProbeFormat(StrEnum):
    SINGLE = "single"
    """Pick exactly one option. Picking several scores 0."""
    MULTI = "multi"
    """Select all options that apply (possibly none)."""
    VALUE = "value"
    """Give one exact value, normalized by :class:`ValueKind`."""
    LIST = "list"
    """Give every value in a set, normalized by :class:`ValueKind`."""


class ValueKind(StrEnum):
    TEXT = "text"
    NUMBER = "number"
    MONEY = "money"
    DATE = "date"
    IDENT = "ident"
    VERSION = "version"
    NAME = "name"


class ProbeCategory(StrEnum):
    CONSTRAINT_RECALL = "constraint_recall"
    CONSTRAINT_APPLICATION = "constraint_application"
    DECISION_STATE = "decision_state"
    ENTITY_ATTRIBUTION = "entity_attribution"
    REFERENCE_RESOLUTION = "reference_resolution"
    FACT_RECALL = "fact_recall"
    TASK_STATE = "task_state"
    ABSTENTION = "abstention"


class Probe(BaseModel):
    """One question the reader must answer from the compacted artifact.

    ``answer`` holds option texts for SINGLE / MULTI probes and raw values for
    VALUE / LIST probes. ``stale`` holds answers that *were* correct at an
    earlier point in the conversation but have since been superseded — picking
    one is counted separately as a stale answer. ``traps`` holds answers that
    only a decoy supports (a rule for another project, a rejected proposal, an
    instruction smuggled in through tool output); picking one counts as trapped.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str = Field(min_length=1, description="Stable across cycles for carried probes.")
    category: ProbeCategory
    format: ProbeFormat
    question: str = Field(min_length=1)
    options: list[str] = Field(default_factory=list)
    answer: list[str] = Field(default_factory=list)
    value_kind: ValueKind = ValueKind.TEXT
    stale: list[str] = Field(default_factory=list)
    traps: list[str] = Field(
        default_factory=list,
        description="Answers supported only by a decoy or an unauthorized source.",
    )
    origin_cycle: int = Field(ge=0, description="Cycle whose turns introduced the information.")
    family: str = Field(
        default="",
        description="Family that asked it, in a mixed case; empty means the case's family.",
    )

    @model_validator(mode="after")
    def _check_shape(self) -> Probe:
        if self.format in (ProbeFormat.SINGLE, ProbeFormat.MULTI):
            if len(self.options) < 2:
                raise ValueError(f"probe {self.key!r}: choice probes need at least 2 options")
            if len(set(self.options)) != len(self.options):
                raise ValueError(f"probe {self.key!r}: duplicate options")
            unknown = [a for a in self.answer if a not in self.options]
            if unknown:
                raise ValueError(f"probe {self.key!r}: answers {unknown} are not options")
            if self.format == ProbeFormat.SINGLE and len(self.answer) != 1:
                raise ValueError(f"probe {self.key!r}: single-choice probes need one answer")
        else:
            if self.options:
                raise ValueError(f"probe {self.key!r}: value probes take no options")
            if self.format == ProbeFormat.VALUE and len(self.answer) != 1:
                raise ValueError(f"probe {self.key!r}: value probes need one answer")
        return self


class CycleSpec(BaseModel):
    """The turns compacted at one cycle and the probes asked afterwards."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    cycle: int = Field(ge=0)
    turns: list[Turn]
    probes: list[Probe]


class GeneratedCase(BaseModel):
    """A concrete benchmark case produced by a scenario family for a given seed."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str
    family: str
    family_version: str
    suite: str
    seed: int
    difficulty: str
    setting: str
    cycles: list[CycleSpec] = Field(min_length=1)

    @model_validator(mode="after")
    def _check_cycles(self) -> GeneratedCase:
        for index, spec in enumerate(self.cycles):
            if spec.cycle != index:
                raise ValueError(f"case {self.case_id!r}: cycle {index} is numbered {spec.cycle}")
        ids = [t.id for spec in self.cycles for t in spec.turns]
        if ids != sorted(ids) or len(set(ids)) != len(ids):
            raise ValueError(f"case {self.case_id!r}: turn ids must be unique and increasing")
        return self

    @property
    def drift_cycles(self) -> int:
        """Number of compactions after the first one."""
        return len(self.cycles) - 1

    def transcript_through(self, cycle: int) -> Transcript:
        """Every turn from cycle 0 up to and including ``cycle`` (the full-context view)."""
        return Transcript(turns=[t for spec in self.cycles[: cycle + 1] for t in spec.turns])

    def truncated(self, drift_cycles: int) -> GeneratedCase:
        """Return a copy keeping only the first ``drift_cycles + 1`` cycles."""
        if drift_cycles < 0:
            raise ValueError(f"drift_cycles must be >= 0, got {drift_cycles}")
        if drift_cycles >= self.drift_cycles:
            return self
        return self.model_copy(update={"cycles": self.cycles[: drift_cycles + 1]})
