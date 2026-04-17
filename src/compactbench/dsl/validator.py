"""Semantic validation for parsed template definitions.

Pydantic handles structural validation (required fields, types, patterns).
This module catches semantic errors that structure alone cannot: undeclared
variable references, unknown generators, duplicate names.
"""

from __future__ import annotations

from collections.abc import Iterator

from compactbench.dsl.errors import TemplateValidationError, UnknownGeneratorError
from compactbench.dsl.generators import get_generator
from compactbench.dsl.models import TemplateDefinition
from compactbench.dsl.substitution import extract_references

_DIFFICULTY_REFS = frozenset(
    {
        "difficulty.distractor_turns",
        "difficulty.paraphrase_depth",
        "difficulty.override_timing",
    }
)


def validate_template(template: TemplateDefinition) -> None:
    """Raise :class:`TemplateValidationError` if ``template`` is semantically invalid."""
    _validate_variables(template)
    _validate_evaluation_items(template)
    _validate_references(template)


def _validate_variables(template: TemplateDefinition) -> None:
    seen: set[str] = set()
    for var in template.variables:
        if var.name in seen:
            raise TemplateValidationError(f"duplicate variable name: {var.name!r}")
        seen.add(var.name)
        try:
            get_generator(var.generator)
        except UnknownGeneratorError as exc:
            raise TemplateValidationError(f"variable {var.name!r}: {exc}") from exc


def _validate_evaluation_items(template: TemplateDefinition) -> None:
    seen: set[str] = set()
    for item in template.evaluation_items:
        if item.key in seen:
            raise TemplateValidationError(f"duplicate evaluation item key: {item.key!r}")
        seen.add(item.key)


def _validate_references(template: TemplateDefinition) -> None:
    declared = {v.name for v in template.variables}

    for source, text in _walk_strings(template):
        for ref in extract_references(text):
            if ref.startswith("difficulty."):
                if ref not in _DIFFICULTY_REFS:
                    raise TemplateValidationError(
                        f"unknown difficulty reference {{{{{ref}}}}} at {source}. "
                        f"Allowed: {sorted(_DIFFICULTY_REFS)}"
                    )
            elif ref not in declared:
                raise TemplateValidationError(
                    f"reference to undeclared variable {{{{{ref}}}}} at {source}. "
                    f"Declared: {sorted(declared)}"
                )


def _walk_strings(template: TemplateDefinition) -> Iterator[tuple[str, str]]:
    """Yield ``(location, text)`` pairs for every template string that may carry refs."""
    for i, turn in enumerate(template.transcript.turns):
        if turn.template is not None:
            yield f"transcript.turns[{i}].template", turn.template
        if isinstance(turn.count, str):
            yield f"transcript.turns[{i}].count", turn.count

    for gt_field in (
        "immutable_facts",
        "locked_decisions",
        "forbidden_behaviors",
        "unresolved_items",
        "deferred_items",
    ):
        for i, s in enumerate(getattr(template.ground_truth, gt_field)):
            yield f"ground_truth.{gt_field}[{i}]", s

    for k, v in template.ground_truth.entity_map.items():
        yield f"ground_truth.entity_map[{k!r}].key", k
        yield f"ground_truth.entity_map[{k!r}].value", v

    for i, item in enumerate(template.evaluation_items):
        yield f"evaluation_items[{i}].prompt", item.prompt
        for k, v in item.expected.items():
            if isinstance(v, str):
                yield f"evaluation_items[{i}].expected[{k!r}]", v
