"""Provider-native compaction: the compaction features model vendors ship, run as-is.

``anthropic-compaction`` calls Anthropic's server-side on-demand compaction
(beta ``compact-2026-09-04``) with its default summarization prompt. The API
returns a readable summary plus a signed block; the next cycle sends that
block followed by the new turns and compacts again — the same loop an agent
using the feature runs. The summary is used as-is: no budget instruction is
added, so a summary longer than the run's budget is cut off like any other
artifact. Set ``instructions`` in the method config to replace the default
prompt.

OpenAI's Responses compaction returns an encrypted item that only OpenAI
models can read, so it can't be scored by a fixed reader from another
provider and has no built-in here.
"""

from __future__ import annotations

from typing import Any, ClassVar

from compactbench.compactors._utils import output_tokens
from compactbench.compactors.base import Compactor
from compactbench.compactors.errors import CompactorError
from compactbench.contracts import CompactionArtifact, CompactionRequest, TurnRole
from compactbench.providers import AnthropicProvider, CountingProvider, Provider


def _anthropic(provider: Provider) -> AnthropicProvider:
    base = provider.wrapped if isinstance(provider, CountingProvider) else provider
    if not isinstance(base, AnthropicProvider):
        raise CompactorError(
            "anthropic-compaction needs --provider anthropic (it calls Anthropic's "
            f"server-side compaction), got {base.key!r}"
        )
    return base


class AnthropicCompactionCompactor(Compactor):
    """Anthropic server-side on-demand compaction, default prompt."""

    name: ClassVar[str] = "anthropic-compaction"
    version: ClassVar[str] = "1.0.0"

    async def compact(self, request: CompactionRequest) -> CompactionArtifact:
        provider = _anthropic(self.provider)
        messages: list[dict[str, Any]] = []
        previous_block: object = (
            request.previous_artifact.method_metadata.get("compaction_block")
            if request.previous_artifact is not None
            else None
        )
        if isinstance(previous_block, dict):
            messages.append({"role": "assistant", "content": [previous_block]})
        for turn in request.turns:
            if turn.role == TurnRole.ASSISTANT:
                messages.append({"role": "assistant", "content": turn.content})
            elif turn.role == TurnRole.TOOL:
                label = f"TOOL[{turn.name}]" if turn.name else "TOOL"
                messages.append({"role": "user", "content": f"{label}: {turn.content}"})
            else:
                messages.append({"role": "user", "content": turn.content})

        instructions = self.config.get("instructions")
        block, usage = await provider.summarize(
            model=self.model,
            messages=messages,
            max_tokens=output_tokens(request),
            instructions=instructions if isinstance(instructions, str) else None,
        )
        if isinstance(self.provider, CountingProvider):
            await self.provider.record(usage)
        summary = block.get("content")
        return CompactionArtifact(
            summaryText=summary if isinstance(summary, str) else "",
            selectedSourceTurnIds=[t.id for t in request.turns],
            methodMetadata={
                "method": self.name,
                "version": self.version,
                "model": self.model,
                "provider": "anthropic",
                "calls": 1,
                "compaction_block": block,
                "prompt_tokens": usage.prompt_tokens,
                "completion_tokens": usage.completion_tokens,
            },
        )
