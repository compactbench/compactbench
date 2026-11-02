"""What a compactor receives at each cycle."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from compactbench.contracts.artifact import CompactionArtifact
from compactbench.contracts.case import Turn


class CompactionRequest(BaseModel):
    """Input to :meth:`compactbench.compactors.Compactor.compact`.

    This mirrors how compaction works in a real agent: once a conversation has
    been compacted, the original turns are gone. At cycle 0 ``turns`` is the
    whole opening conversation and ``previous_artifact`` is ``None``. At every
    later cycle ``previous_artifact`` is what the method returned last time and
    ``turns`` holds only what happened since — never the earlier turns.

    ``token_budget`` is the maximum size of the rendered artifact (cl100k_base
    tokens). Anything beyond it is cut off before the reader sees it, and
    ranked runs reject any over-budget cycle.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    cycle: int = Field(ge=0)
    turns: list[Turn]
    previous_artifact: CompactionArtifact | None = None
    token_budget: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def _check_previous(self) -> CompactionRequest:
        if self.cycle == 0 and self.previous_artifact is not None:
            raise ValueError("cycle 0 has no previous artifact")
        if self.cycle > 0 and self.previous_artifact is None:
            raise ValueError(f"cycle {self.cycle} needs the previous artifact")
        return self
