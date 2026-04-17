"""Deterministic case generation from template + seed.

Implements WO-003 per docs/architecture/decisions.md §B1.
"""

from compactbench.engine.difficulty import (
    difficulty_bindings,
    distractor_count_for,
    override_timing_for,
    paraphrase_depth_for,
)
from compactbench.engine.distractors import generate_distractor_turns
from compactbench.engine.errors import EngineError, GenerationError
from compactbench.engine.generation import generate_case
from compactbench.engine.seeds import derive_case_seed
from compactbench.engine.transcript import build_transcript

__all__ = [
    "EngineError",
    "GenerationError",
    "build_transcript",
    "derive_case_seed",
    "difficulty_bindings",
    "distractor_count_for",
    "generate_case",
    "generate_distractor_turns",
    "override_timing_for",
    "paraphrase_depth_for",
]
