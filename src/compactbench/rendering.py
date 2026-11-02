"""Plain-text rendering shared by compactors, the reader, and token accounting.

The reader only ever sees :func:`render_artifact` output, and budgets and
compression ratios are measured on that same text, so a method cannot hide
content in fields the reader doesn't see or the budget doesn't count.
"""

from __future__ import annotations

from compactbench.contracts import CompactionArtifact, CompactionRequest, StructuredState, Turn
from compactbench.contracts.case import TurnRole


def render_turn(turn: Turn) -> str:
    """Render one turn as ``ROLE: content`` (``TOOL[name]: content`` for tool output)."""
    if turn.role == TurnRole.TOOL:
        label = f"TOOL[{turn.name}]" if turn.name else "TOOL"
    else:
        label = turn.role.value.upper()
    return f"{label}: {turn.content}"


def render_turns(turns: list[Turn]) -> str:
    """Render turns separated by blank lines."""
    return "\n\n".join(render_turn(t) for t in turns)


def render_artifact(artifact: CompactionArtifact) -> str:
    """Render an artifact exactly as the reader will see it."""
    blocks: list[str] = []
    if artifact.summary_text.strip():
        blocks.append(f"SUMMARY:\n{artifact.summary_text.strip()}")
    state_block = render_state(artifact.structured_state)
    if state_block:
        blocks.append("STRUCTURED STATE:\n" + state_block)
    return "\n\n".join(blocks)


def render_state(state: StructuredState) -> str:
    """Render the structured state sections that have content."""
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


def render_request(request: CompactionRequest) -> str:
    """Render a compaction request as one prompt body.

    Cycle 0 renders just the conversation. Later cycles render the previous
    artifact first, then the turns that happened since it was made.
    """
    conversation = render_turns(request.turns) if request.turns else "(no new turns)"
    if request.previous_artifact is None:
        return f"CONVERSATION:\n{conversation}"
    previous = render_artifact(request.previous_artifact) or "(empty)"
    return (
        "PREVIOUSLY COMPACTED CONTEXT (everything before the new turns):\n"
        f"{previous}\n\n"
        "NEW TURNS SINCE THAT COMPACTION:\n"
        f"{conversation}"
    )
