"""Resolve difficulty knobs from a ``DifficultyPolicy`` at generation time."""

from __future__ import annotations

from compactbench.dsl import DifficultyLevel, DifficultyPolicy
from compactbench.engine.errors import GenerationError


def distractor_count_for(policy: DifficultyPolicy, difficulty: DifficultyLevel) -> int:
    """Return the distractor-turn count for ``difficulty``.

    If the policy configures no distractor levels, returns 0. If the policy is
    configured but does not include the chosen level, raises
    :class:`GenerationError`.
    """
    mapping = policy.distractor_turns
    if not mapping:
        return 0
    if difficulty not in mapping:
        raise GenerationError(
            f"template does not configure distractor_turns for difficulty "
            f"{difficulty.value!r}. Configured levels: "
            f"{sorted(lvl.value for lvl in mapping)}"
        )
    return mapping[difficulty]


def paraphrase_depth_for(policy: DifficultyPolicy, difficulty: DifficultyLevel) -> int:
    """Return the paraphrase depth for ``difficulty`` (0 when unconfigured).

    Actual paraphrasing is a no-op in v1; this value is surfaced as a binding
    so templates can reference it, but no transform is applied yet.
    """
    return policy.paraphrase_depth.get(difficulty, 0)


def override_timing_for(policy: DifficultyPolicy, difficulty: DifficultyLevel) -> str:
    """Return the override timing for ``difficulty`` (``""`` when unconfigured).

    Like paraphrase depth, this is a v1 no-op passthrough.
    """
    return policy.override_timing.get(difficulty, "")


def difficulty_bindings(policy: DifficultyPolicy, difficulty: DifficultyLevel) -> dict[str, str]:
    """Return bindings for ``difficulty.*`` references in template strings."""
    bindings: dict[str, str] = {
        "difficulty.paraphrase_depth": str(paraphrase_depth_for(policy, difficulty)),
        "difficulty.override_timing": override_timing_for(policy, difficulty),
    }
    # distractor_turns may not be configured; bind the literal string form when it is.
    if policy.distractor_turns:
        bindings["difficulty.distractor_turns"] = str(distractor_count_for(policy, difficulty))
    return bindings
