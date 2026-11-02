"""Extractive baseline: keep the sentences that look like state, with no model at all.

Each cycle splits the new turns into sentences, keeps the ones carrying a state
signal — a decision, rule, owner, status, date, amount or identifier — and
appends them to the previous artifact's lines. When the result is over budget,
the oldest lines go first, since later statements supersede earlier ones.

It costs nothing to run and shows how far pattern matching gets without
understanding: it can't tell a rule from a rejected proposal, or a team decision
from a claim in a fetched document.
"""

from __future__ import annotations

import re
from typing import ClassVar

from compactbench.compactors.base import Compactor
from compactbench.contracts import CompactionArtifact, CompactionRequest, StructuredState
from compactbench.tokens import count_tokens

_SIGNAL = re.compile(
    r"\b(decid\w*|decision|final|going with|we'll use|switch\w*|replac\w*|revert\w*|"
    r"instead of|approv\w*|reject\w*|owns?|owner|taking over|handover|assign\w*|"
    r"blocked|unblocked|in review|in progress|done|reopen\w*|rule|must|never|always|"
    r"without|until|freeze|cap(ped)?|limit|at most|no more than|deadline|contract|"
    r"budget|lifted|no longer|applies|covers?|exception|carve-out|confirmed|correction)\b"
    r"|\$\d|\d{4}-\d{2}-\d{2}|\b[A-Z]{2,}-\d+\b|\bv?\d+\.\d+(\.\d+)?\b",
    re.IGNORECASE,
)
_SENTENCE = re.compile(r"(?<=[.!?])\s+|\n+")
_MAX_LINE = 300


class ExtractiveCompactor(Compactor):
    """Baseline: pattern-matched sentence extraction, newest kept within the budget."""

    name: ClassVar[str] = "extractive"
    version: ClassVar[str] = "1.0.0"

    async def compact(self, request: CompactionRequest) -> CompactionArtifact:
        previous = request.previous_artifact
        lines = previous.summary_text.splitlines() if previous and previous.summary_text else []
        seen = set(lines)
        for turn in request.turns:
            for sentence in _SENTENCE.split(turn.content):
                text = " ".join(sentence.split())[:_MAX_LINE]
                if len(text) < 12 or text in seen or not _SIGNAL.search(text):
                    continue
                seen.add(text)
                lines.append(text)

        budget = request.token_budget
        dropped = 0
        if budget is not None:
            # Count each line once (plus one for its newline), drop oldest lines first,
            # then confirm on the rendered text, which is what the budget applies to.
            sizes = [count_tokens(line) + 1 for line in lines]
            total = sum(sizes) + count_tokens("SUMMARY:\n")
            while lines and total > budget:
                total -= sizes.pop(0)
                lines.pop(0)
                dropped += 1
            while lines and count_tokens("SUMMARY:\n" + "\n".join(lines)) > budget:
                lines.pop(0)
                dropped += 1
        return CompactionArtifact(
            summaryText="\n".join(lines),
            structured_state=StructuredState(),
            selectedSourceTurnIds=[t.id for t in request.turns],
            warnings=[f"dropped {dropped} oldest lines to fit the budget"] if dropped else [],
            methodMetadata={"method": self.name, "version": self.version, "calls": 0},
        )
