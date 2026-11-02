"""Helpers used across compactor implementations."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from compactbench.contracts import CompactionArtifact, CompactionRequest, StructuredState
from compactbench.providers import ReasoningEffort
from compactbench.rendering import render_artifact
from compactbench.tokens import count_tokens, head_tokens

T = TypeVar("T")

# Rough words-per-token ratio for English prose under cl100k_base. Only used to
# phrase a length instruction for the model, never to enforce the budget.
_WORDS_PER_TOKEN = 0.7


def budget_instruction(request: CompactionRequest, *, share: float = 1.0) -> str:
    """Return a length instruction for ``share`` of the request's token budget."""
    if request.token_budget is None:
        return "Be concise."
    words = max(30, int(request.token_budget * share * _WORDS_PER_TOKEN))
    return f"Stay under {words} words — anything longer is cut off."


DEFAULT_EFFORT: ReasoningEffort = "low"
_EFFORTS = ("low", "medium", "high")


def reasoning_effort(config: Mapping[str, Any]) -> ReasoningEffort | None:
    """Effort for a built-in method's own model calls.

    ``config["effort"]`` picks it (``null`` leaves it to the model's default).
    Every built-in uses the same default, ``low``, so baselines are compared at
    one setting; set ``effort`` in the method config to change it.
    """
    value = config.get("effort", DEFAULT_EFFORT)
    if value is None:
        return None
    if value not in _EFFORTS:
        raise ValueError(f"effort must be one of {_EFFORTS} or null, got {value!r}")
    return value


def output_tokens(request: CompactionRequest) -> int:
    """``max_tokens`` for a call that writes the artifact (or a large part of it).

    A cap, not a target — only the tokens used are billed. It leaves room for
    reasoning on top of the artifact itself.
    """
    del request  # same cap at every budget: reasoning, not the artifact, dominates
    return 16_000


_SECTIONS = (
    "locked_decisions",
    "forbidden_behaviors",
    "immutable_facts",
    "unresolved_items",
    "deferred_items",
)


def fit_to_budget(
    artifact: CompactionArtifact, budget: int | None
) -> tuple[CompactionArtifact, list[str]]:
    """Trim ``artifact`` until its rendering fits ``budget`` tokens.

    Drops the oldest entries of the largest structured section first, then
    entity-map entries, then the tail of the summary — so a method that
    accumulates state degrades gracefully instead of being cut off mid-text.
    Returns the fitted artifact and a warning when anything was dropped.
    """
    if budget is None or count_tokens(render_artifact(artifact)) <= budget:
        return artifact, []
    state = artifact.structured_state
    lists: dict[str, list[str]] = {name: list(getattr(state, name)) for name in _SECTIONS}
    entities = dict(state.entity_map)
    summary = artifact.summary_text

    def rebuilt() -> CompactionArtifact:
        return artifact.model_copy(
            update={
                "summary_text": summary,
                "structured_state": StructuredState(**lists, entity_map=entities),
            }
        )

    dropped = 0
    candidate = rebuilt()
    while count_tokens(render_artifact(candidate)) > budget:
        non_empty = [name for name in _SECTIONS if lists[name]]
        if non_empty:
            largest = max(non_empty, key=lambda name: sum(count_tokens(i) for i in lists[name]))
            lists[largest].pop(0)
        elif entities:
            entities.pop(next(iter(entities)))
        else:
            overflow = count_tokens(render_artifact(candidate)) - budget
            summary = head_tokens(summary, max(count_tokens(summary) - overflow - 8, 0))
            candidate = rebuilt()
            break
        dropped += 1
        candidate = rebuilt()
    return candidate, [f"trimmed to fit the {budget}-token budget ({dropped} entries dropped)"]


def finalize(artifact: CompactionArtifact, request: CompactionRequest) -> CompactionArtifact:
    """Fit ``artifact`` to the request's budget, recording any trimming as a warning."""
    fitted, trimmed = fit_to_budget(artifact, request.token_budget)
    if not trimmed:
        return fitted
    return fitted.model_copy(update={"warnings": [*fitted.warnings, *trimmed][-50:]})


def chunk(items: list[T], size: int) -> list[list[T]]:
    """Split ``items`` into groups of ``size`` (last group may be smaller)."""
    if size <= 0:
        raise ValueError(f"chunk size must be > 0, got {size}")
    return [items[i : i + size] for i in range(0, len(items), size)]


def uniq_preserve_order(items: list[str]) -> list[str]:
    """Return ``items`` with duplicates removed, preserving first-occurrence order."""
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


#: Maximum characters ``CompactionArtifact.summary_text`` accepts. Mirrored here
#: so compactors can fit their output *before* constructing the artifact rather
#: than discovering the limit as a pydantic ValidationError.
SUMMARY_TEXT_LIMIT = 200_000


def fit_summary_text(text: str, *, limit: int = SUMMARY_TEXT_LIMIT) -> tuple[str, list[str]]:
    """Trim ``text`` to the artifact's summary cap, reporting whether it cut.

    The cap is a sanity limit far above any token budget; budgets are enforced
    separately on the rendered artifact. Truncating instead of raising matters
    because a model that ignores its length instruction — which small and local
    models routinely do — would otherwise raise a ``ValidationError`` that
    aborts the **entire run**, losing every other case to one verbose response.
    The truncation is recorded in the artifact's ``warnings`` so it shows up in
    ``results.jsonl``.
    """
    if len(text) <= limit:
        return text, []
    return text[:limit], [
        f"summary_text exceeded the {limit}-character artifact limit "
        f"({len(text)} chars) and was truncated; the method should compress further"
    ]
