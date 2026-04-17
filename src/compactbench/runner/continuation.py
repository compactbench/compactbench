"""Extend a transcript with continuation turns for drift-cycle testing.

At each drift cycle we:
1. Append a seeded user continuation prompt.
2. Ask the target model for an assistant response *using only the previous
   compacted artifact as context* — that is the drift vector we care about.
3. Append both turns to the transcript and hand it back for re-compaction.
"""

from __future__ import annotations

import random

from compactbench.contracts import CompactionArtifact, Transcript, Turn, TurnRole
from compactbench.dsl import derive_seed
from compactbench.providers import CompletionRequest, Provider
from compactbench.runner.evaluation import render_artifact_for_prompt

_CONTINUATION_PROMPTS: tuple[str, ...] = (
    "What should we tackle next?",
    "Given everything we've discussed, what's the priority?",
    "Any considerations I might be missing?",
    "What could go wrong with the current plan?",
    "Anything else to wire in before we move on?",
    "Walk me through the immediate next step.",
    "Which risk concerns you most right now?",
    "Who needs to be looped in before we proceed?",
)


def select_continuation_prompt(case_seed: int, cycle_number: int) -> str:
    """Pick a deterministic user prompt for the given cycle."""
    sub_seed = derive_seed(case_seed, f"continuation_prompt_{cycle_number}")
    rng = random.Random(sub_seed)
    return rng.choice(_CONTINUATION_PROMPTS)


def build_continuation_prompt(artifact: CompactionArtifact, user_content: str) -> str:
    """Build the prompt asking the target model for an assistant response."""
    context = render_artifact_for_prompt(artifact)
    return (
        "You have the following summary of a prior conversation:\n\n"
        f"{context}\n\n"
        "The user now says:\n\n"
        f"USER: {user_content}\n\n"
        "Respond as the assistant. Your response will be treated as the next "
        "assistant turn in the ongoing conversation.\n\n"
        "ASSISTANT:"
    )


async def extend_with_continuation(
    transcript: Transcript,
    previous_artifact: CompactionArtifact,
    provider: Provider,
    model: str,
    case_seed: int,
    cycle_number: int,
) -> Transcript:
    """Return a transcript extended with one (user, assistant) continuation pair."""
    user_content = select_continuation_prompt(case_seed, cycle_number)
    assistant_prompt = build_continuation_prompt(previous_artifact, user_content)
    response = await provider.complete(CompletionRequest(model=model, prompt=assistant_prompt))

    next_id = (max((t.id for t in transcript.turns), default=-1)) + 1
    user_turn = Turn(
        id=next_id,
        role=TurnRole.USER,
        content=user_content,
        tags=["continuation"],
    )
    assistant_turn = Turn(
        id=next_id + 1,
        role=TurnRole.ASSISTANT,
        content=response.text.strip(),
        tags=["continuation"],
    )
    return Transcript(turns=[*transcript.turns, user_turn, assistant_turn])
