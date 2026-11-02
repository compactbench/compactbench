"""Provider-native compaction built-ins, offline."""

from __future__ import annotations

from typing import Any

import pytest

from compactbench.compactors import AnthropicCompactionCompactor, CompactorError
from compactbench.contracts import TokenUsage, Transcript, Turn, TurnRole
from compactbench.providers import AnthropicProvider, CountingProvider, MockProvider
from tests.helpers import first_request, next_request

pytestmark = pytest.mark.unit


class _FakeAnthropic(AnthropicProvider):
    def __init__(self) -> None:
        super().__init__(api_key="test-key")
        self.calls: list[dict[str, Any]] = []

    async def summarize(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        max_tokens: int,
        instructions: str | None = None,
    ) -> tuple[dict[str, Any], TokenUsage]:
        self.calls.append({"messages": messages, "instructions": instructions})
        n = len(self.calls)
        block = {"type": "compaction", "content": f"summary {n}", "signature": f"sig{n}"}
        return block, TokenUsage(prompt_tokens=100, completion_tokens=20, call_count=1)


def _turns(*pairs: tuple[TurnRole, str], start: int = 0) -> Transcript:
    return Transcript(
        turns=[
            Turn(
                id=start + i,
                role=role,
                content=text,
                name="run_tests" if role == TurnRole.TOOL else None,
            )
            for i, (role, text) in enumerate(pairs)
        ]
    )


async def test_summary_becomes_the_artifact_and_usage_is_counted() -> None:
    fake = _FakeAnthropic()
    counting = CountingProvider(fake)
    compactor = AnthropicCompactionCompactor(counting, "claude-haiku-5-5")
    artifact = await compactor.compact(
        first_request(_turns((TurnRole.USER, "hi"), (TurnRole.TOOL, "3 passed")))
    )
    assert artifact.summary_text == "summary 1"
    assert fake.calls[0]["messages"][1] == {"role": "user", "content": "TOOL[run_tests]: 3 passed"}
    usage = await counting.snapshot()
    assert usage.call_count == 1
    assert usage.prompt_tokens == 100


async def test_compacts_again_from_the_signed_block() -> None:
    fake = _FakeAnthropic()
    compactor = AnthropicCompactionCompactor(fake, "claude-haiku-5-5")
    first = await compactor.compact(first_request(_turns((TurnRole.USER, "a"))))
    await compactor.compact(next_request(_turns((TurnRole.ASSISTANT, "b"), start=1), first))
    messages = fake.calls[1]["messages"]
    assert messages[0] == {
        "role": "assistant",
        "content": [{"type": "compaction", "content": "summary 1", "signature": "sig1"}],
    }
    assert messages[1] == {"role": "assistant", "content": "b"}


async def test_custom_instructions_from_config() -> None:
    fake = _FakeAnthropic()
    compactor = AnthropicCompactionCompactor(fake, "m", {"instructions": "keep every rule"})
    await compactor.compact(first_request(_turns((TurnRole.USER, "a"))))
    assert fake.calls[0]["instructions"] == "keep every rule"


async def test_needs_the_anthropic_provider() -> None:
    compactor = AnthropicCompactionCompactor(MockProvider(), "m")
    with pytest.raises(CompactorError, match="--provider anthropic"):
        await compactor.compact(first_request(_turns((TurnRole.USER, "a"))))
