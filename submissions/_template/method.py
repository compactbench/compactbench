"""Your compaction method.

This file ships as a working example — it runs and produces a valid artifact
out of the box (a running summary). Replace the body of ``compact`` with
something better and rename the class + ``name`` to match.

How compaction works here: at cycle 0 ``request.turns`` is the whole opening
conversation. At every later cycle ``request.previous_artifact`` is what you
returned last time and ``request.turns`` holds ONLY the turns since then — the
earlier conversation is gone, exactly as in a real agent. Keep the rendered
artifact under ``request.token_budget`` tokens or it is cut off.

Test it locally against the public Practice suite with any model — a local one
through Ollama, a hosted one, or your own OpenAI-compatible server:

    compactbench run --method method.py:MyCompactor --suite practice --cases 4 \\
        --provider ollama --model qwen2.5:7b-instruct --controls --output results.jsonl
    compactbench qualify --results results.jsonl

Ranked submissions are paused while the v2 evaluation pipeline is finished.

Full API docs: docs/writing-a-compactor.md in https://github.com/compactbench/compactbench
"""

from __future__ import annotations

from typing import ClassVar

from compactbench.compactors import Compactor, fit_to_budget
from compactbench.contracts import CompactionArtifact, CompactionRequest, StructuredState
from compactbench.providers import CompletionRequest
from compactbench.rendering import render_request


class MyCompactor(Compactor):
    """One-line description of what your method does.

    Longer description: what's novel, what tradeoffs you're making, what you
    expect to score well on.
    """

    name: ClassVar[str] = "my-method"
    version: ClassVar[str] = "0.1.0"

    async def compact(self, request: CompactionRequest) -> CompactionArtifact:
        # ~0.7 words per token, aiming well under the budget so trimming is rare.
        words = int((request.token_budget or 2000) * 0.5)
        response = await self.provider.complete(
            CompletionRequest(
                model=self.model,
                # A cap, not a target: reasoning models think before they write, and a
                # small cap can run out before any text. Low effort keeps thinking short.
                max_tokens=8_000,
                reasoning_effort="low",
                prompt=(
                    "Update the running summary of this conversation. Keep every rule, "
                    "decision (and what it replaced), owner, number and identifier that "
                    f"still matters. Stay under {words} words.\n\n{render_request(request)}"
                ),
            )
        )
        artifact = CompactionArtifact(
            summaryText=response.text.strip(),
            structured_state=StructuredState(),
            selectedSourceTurnIds=[t.id for t in request.turns],
            warnings=[],
            methodMetadata={
                "method": self.name,
                "version": self.version,
                "model": self.model,
                "provider": self.provider.key,
                "calls": 1,
            },
        )
        # Anything over the budget is cut before the reader sees it, and a ranked run with
        # an over-budget artifact doesn't qualify. fit_to_budget drops the oldest structured
        # entries first, then the end of the summary.
        fitted, _ = fit_to_budget(artifact, request.token_budget)
        return fitted
