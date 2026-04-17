"""Distractor turn generation.

Distractor blocks expand into plausible-sounding off-topic conversational
turns. Their purpose is to act as noise between critical turns so the
compactor has to filter signal from filler.

Content is drawn from bounded lexicons and alternates user/assistant.
"""

from __future__ import annotations

import random

from compactbench.contracts import Turn, TurnRole

_USER_DISTRACTORS: tuple[str, ...] = (
    "By the way, how long have you been working with me today?",
    "Quick question unrelated to this: what time is it where you are?",
    "I just remembered I need to send someone an email later.",
    "Random thought: do you have opinions on coffee versus tea?",
    "Oh, did you see that article about electric cars?",
    "Side note — my internet has been slow today.",
    "What's the weather like lately?",
    "Unrelated, but what do you think of remote work in general?",
    "By the way, do you read much fiction?",
    "Quick tangent: is it true that pandas have thumbs?",
    "I was thinking about lunch earlier.",
    "Off-topic, but any thoughts on daylight saving time?",
    "Random: I keep hearing about this one podcast.",
    "Unrelated question — do you know anything about gardening?",
    "Do you happen to know what a quokka is?",
)

_ASSISTANT_DISTRACTORS: tuple[str, ...] = (
    "Happy to chat about that briefly — anything else on the main topic?",
    "I can answer, but let me know when you want to return to the main question.",
    "Quick aside, sure. Anything else pressing?",
    "Got it. Let me know if you want to switch focus back.",
    "Sure, I can address that. Is there anything more on the main thread?",
    "Understood. Shall we continue where we left off?",
    "Acknowledged. Ready when you are to move forward.",
    "Fair point. Want me to refocus on the earlier question?",
    "Noted. Do you want to get back to the plan?",
    "I hear you. Anything else to cover on the primary question?",
)


def generate_distractor_turns(count: int, starting_turn_id: int, seed: int) -> list[Turn]:
    """Produce ``count`` distractor turns alternating user/assistant.

    IDs start at ``starting_turn_id`` and increment by one. Role alternation
    starts with ``user``.
    """
    if count < 0:
        raise ValueError(f"count must be >= 0, got {count}")
    if count == 0:
        return []
    rng = random.Random(seed)
    turns: list[Turn] = []
    for i in range(count):
        turn_id = starting_turn_id + i
        if i % 2 == 0:
            role = TurnRole.USER
            content = rng.choice(_USER_DISTRACTORS)
        else:
            role = TurnRole.ASSISTANT
            content = rng.choice(_ASSISTANT_DISTRACTORS)
        turns.append(Turn(id=turn_id, role=role, content=content, tags=["distractor"]))
    return turns
