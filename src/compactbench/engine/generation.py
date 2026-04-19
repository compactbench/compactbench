"""Top-level case generation: ``TemplateDefinition`` + seed + difficulty -> ``GeneratedCase``."""

from __future__ import annotations

from typing import Any

from compactbench.contracts import (
    EvaluationItem,
    EvaluationItemType,
    GeneratedCase,
    GroundTruth,
)
from compactbench.dsl import (
    DifficultyLevel,
    EvaluationItemTemplate,
    GroundTruthTemplate,
    TemplateDefinition,
    resolve_variables,
    substitute,
)
from compactbench.engine.difficulty import difficulty_bindings
from compactbench.engine.errors import GenerationError
from compactbench.engine.transcript import build_transcript


def generate_case(
    template: TemplateDefinition,
    seed: int,
    difficulty: DifficultyLevel = DifficultyLevel.MEDIUM,
    *,
    case_id: str | None = None,
) -> GeneratedCase:
    """Generate a concrete :class:`GeneratedCase` from a template, seed, and difficulty.

    Pure function of its inputs. No filesystem, network, or global state is
    touched beyond the module-level generator registry in
    :mod:`compactbench.dsl.generators`.
    """
    bindings = resolve_variables(list(template.variables), seed)
    bindings.update(difficulty_bindings(template.difficulty_policy, difficulty))

    transcript = build_transcript(template, bindings, seed, difficulty)
    ground_truth = _build_ground_truth(template.ground_truth, bindings)
    evaluation_items = _build_evaluation_items(template.evaluation_items, bindings)

    return GeneratedCase(
        case_id=case_id or f"{template.key}:s{seed}:d{difficulty.value}",
        template_key=template.key,
        template_version=template.version,
        seed=seed,
        difficulty=difficulty.value,
        transcript=transcript,
        ground_truth=ground_truth,
        evaluation_items=evaluation_items,
    )


def _build_ground_truth(template: GroundTruthTemplate, bindings: dict[str, str]) -> GroundTruth:
    def _sub_list(items: list[str]) -> list[str]:
        return [substitute(s, bindings) for s in items]

    return GroundTruth(
        immutable_facts=_sub_list(template.immutable_facts),
        locked_decisions=_sub_list(template.locked_decisions),
        forbidden_behaviors=_sub_list(template.forbidden_behaviors),
        unresolved_items=_sub_list(template.unresolved_items),
        deferred_items=_sub_list(template.deferred_items),
        entity_map={
            substitute(k, bindings): substitute(v, bindings) for k, v in template.entity_map.items()
        },
    )


def _build_evaluation_items(
    templates: list[EvaluationItemTemplate], bindings: dict[str, str]
) -> list[EvaluationItem]:
    results: list[EvaluationItem] = []
    for item in templates:
        try:
            item_type = EvaluationItemType(item.type)
        except ValueError as exc:
            raise GenerationError(
                f"evaluation item {item.key!r}: unknown type {item.type!r}. "
                f"Known: {[t.value for t in EvaluationItemType]}"
            ) from exc
        expected: dict[str, Any] = {}
        for k, v in item.expected.items():
            expected[k] = substitute(v, bindings) if isinstance(v, str) else v
        results.append(
            EvaluationItem(
                key=item.key,
                item_type=item_type,
                prompt=substitute(item.prompt, bindings),
                expected=expected,
            )
        )
    return results
