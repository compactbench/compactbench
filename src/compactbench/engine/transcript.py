"""Build a concrete :class:`Transcript` from a template and bindings."""

from __future__ import annotations

from compactbench.contracts import Transcript, Turn, TurnRole
from compactbench.dsl import (
    DifficultyLevel,
    TemplateDefinition,
    TemplateTurnRole,
    derive_seed,
    extract_references,
    substitute,
)
from compactbench.engine.difficulty import distractor_count_for
from compactbench.engine.distractors import generate_distractor_turns
from compactbench.engine.errors import GenerationError

_TEMPLATE_TO_TURN_ROLE: dict[TemplateTurnRole, TurnRole] = {
    TemplateTurnRole.USER: TurnRole.USER,
    TemplateTurnRole.ASSISTANT: TurnRole.ASSISTANT,
    TemplateTurnRole.SYSTEM: TurnRole.SYSTEM,
}


def build_transcript(
    template: TemplateDefinition,
    bindings: dict[str, str],
    case_seed: int,
    difficulty: DifficultyLevel,
) -> Transcript:
    """Expand a template transcript into concrete turns with variables resolved."""
    turns: list[Turn] = []
    next_id = 0

    for index, template_turn in enumerate(template.transcript.turns):
        if template_turn.role is TemplateTurnRole.DISTRACTOR_BLOCK:
            count = _resolve_count(
                template_turn.count,
                template,
                difficulty,
                location=f"transcript.turns[{index}].count",
            )
            sub_seed = derive_seed(case_seed, f"distractor_block_{index}")
            turns.extend(generate_distractor_turns(count, next_id, sub_seed))
            next_id += count
            continue

        if template_turn.template is None:
            raise GenerationError(
                f"transcript.turns[{index}] has role {template_turn.role.value!r} "
                f"but no 'template' field"
            )
        content = substitute(template_turn.template, bindings)
        turns.append(
            Turn(
                id=next_id,
                role=_TEMPLATE_TO_TURN_ROLE[template_turn.role],
                content=content,
                tags=list(template_turn.tags),
            )
        )
        next_id += 1

    return Transcript(turns=turns)


def _resolve_count(
    count: str | int | None,
    template: TemplateDefinition,
    difficulty: DifficultyLevel,
    *,
    location: str,
) -> int:
    if count is None:
        raise GenerationError(f"{location}: missing count for distractor_block")
    if isinstance(count, int):
        if count < 0:
            raise GenerationError(f"{location}: negative count {count}")
        return count

    refs = extract_references(count)
    if refs == ["difficulty.distractor_turns"]:
        return distractor_count_for(template.difficulty_policy, difficulty)
    raise GenerationError(f"{location}: unsupported count expression {count!r}")
