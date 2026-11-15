"""A CompactBench method wrapping your own compaction.

Check it with:  compactbench check --method compactor_template.py:MyCompaction --estimate
"""

from __future__ import annotations

from typing import ClassVar

from compactbench.compactors import Compactor, fit_to_budget
from compactbench.contracts import CompactionArtifact, CompactionRequest
from compactbench.providers import CompletionRequest
from compactbench.rendering import render_request

# Option A: your compaction instructions, sent with the conversation to --provider/--model.
INSTRUCTIONS = """Your context is being compacted. Write the summary you will continue from;
the original messages will not be available."""


class MyCompaction(Compactor):
    name: ClassVar[str] = "my-compaction"
    version: ClassVar[str] = "0.1.0"

    async def compact(self, request: CompactionRequest) -> CompactionArtifact:
        # First compaction: request.turns is the whole conversation.
        # Later ones: request.previous_artifact is this method's last output and
        # request.turns only the turns since then. render_request() renders both as text.
        limit = f"Stay under {request.token_budget} tokens." if request.token_budget else ""
        response = await self.provider.complete(
            CompletionRequest(
                model=self.model,
                prompt=f"{INSTRUCTIONS}\n{limit}\n\n{render_request(request)}\n\nSUMMARY:",
                max_tokens=8_000,  # room for thinking on reasoning models
                reasoning_effort="low",
            )
        )
        summary = response.text.strip()

        # Option B: call your own code instead, for example
        #     summary = await my_app.memory.summarize(render_request(request))
        # (it then uses its own model client and keys; --provider/--model are only recorded).

        artifact = CompactionArtifact(summaryText=summary)
        fitted, _ = fit_to_budget(artifact, request.token_budget)
        return fitted
