"""Build evaluation prompts and issue them against the target model.

After compaction, the target model answers each ``EvaluationItem`` using
*only* the compacted artifact as context. That is the core measurement of
the benchmark: how well state survives compaction.
"""

from __future__ import annotations

from compactbench.contracts import CompactionArtifact, EvaluationItem, StructuredState
from compactbench.providers import CompletionRequest, Provider


def render_artifact_for_prompt(artifact: CompactionArtifact) -> str:
    """Render a compaction artifact as plain text for inclusion in a prompt."""
    blocks: list[str] = []
    if artifact.summary_text:
        blocks.append(f"SUMMARY:\n{artifact.summary_text}")

    state_block = _render_state(artifact.structured_state)
    if state_block:
        blocks.append("STRUCTURED STATE:\n" + state_block)

    return "\n\n".join(blocks) if blocks else "(no summary or structured state)"


def _render_state(state: StructuredState) -> str:
    sections: list[str] = []

    def _list_section(label: str, items: list[str]) -> None:
        if items:
            sections.append(f"{label}:\n" + "\n".join(f"- {s}" for s in items))

    _list_section("Immutable facts", list(state.immutable_facts))
    _list_section("Locked decisions", list(state.locked_decisions))
    _list_section("Forbidden behaviors (NEVER do)", list(state.forbidden_behaviors))
    _list_section("Deferred items", list(state.deferred_items))
    _list_section("Unresolved items", list(state.unresolved_items))

    if state.entity_map:
        entity_lines = "\n".join(f"- {k}: {v}" for k, v in state.entity_map.items())
        sections.append(f"Entity roles:\n{entity_lines}")

    return "\n\n".join(sections)


def build_evaluation_prompt(artifact: CompactionArtifact, item: EvaluationItem) -> str:
    """Compose the prompt sent to the target model for a single evaluation item."""
    context = render_artifact_for_prompt(artifact)
    return (
        "You have the following summary of a prior conversation:\n\n"
        f"{context}\n\n"
        "Based only on this summary, answer the following question concisely.\n\n"
        f"QUESTION: {item.prompt}\n\n"
        "ANSWER:"
    )


async def evaluate_items(
    items: list[EvaluationItem],
    artifact: CompactionArtifact,
    provider: Provider,
    model: str,
) -> dict[str, str]:
    """Invoke the target model on every evaluation item, returning ``{item_key: response}``."""
    responses: dict[str, str] = {}
    for item in items:
        prompt = build_evaluation_prompt(artifact, item)
        response = await provider.complete(CompletionRequest(model=model, prompt=prompt))
        responses[item.key] = response.text.strip()
    return responses
