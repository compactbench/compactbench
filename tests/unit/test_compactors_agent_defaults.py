"""Agents' default compaction: Codex CLI and LangChain's SummarizationMiddleware."""

from __future__ import annotations

import pytest

from compactbench.compactors import get_built_in
from compactbench.compactors.agent_defaults import (
    CODEX_PROMPT,
    CODEX_SUMMARY_PREFIX,
    LANGCHAIN_SUMMARY_HEADER,
    CodexCliCompactor,
    LangChainSummarizationCompactor,
    trim_last_messages,
)
from compactbench.contracts import CompactionRequest, Turn, TurnRole
from compactbench.providers.mock import MockProvider
from compactbench.rendering import render_artifact
from compactbench.tokens import count_tokens

pytestmark = pytest.mark.unit


def _chat(*texts: str, start: int = 0) -> list[Turn]:
    """Alternating user / assistant turns."""
    roles = (TurnRole.USER, TurnRole.ASSISTANT)
    return [Turn(id=start + i, role=roles[i % 2], content=text) for i, text in enumerate(texts)]


def test_both_are_built_ins() -> None:
    assert get_built_in("codex-cli") is CodexCliCompactor
    assert get_built_in("langchain-summarization") is LangChainSummarizationCompactor


async def test_codex_sends_its_prompt_after_the_history_and_keeps_recent_user_messages() -> None:
    provider = MockProvider(default="Progress: chose Postgres. Next: migrate.")
    compactor = CodexCliCompactor(provider, "m")
    turns = _chat("We use Postgres.", "Noted.", "Owner is Ana.", "OK.", "Ship Friday.", "Sure.")
    artifact = await compactor.compact(CompactionRequest(cycle=0, turns=turns, token_budget=1024))

    prompt = provider.calls[0].prompt
    assert prompt.index("We use Postgres.") < prompt.index(CODEX_PROMPT)
    assert "Stay under" in prompt.split(CODEX_PROMPT)[1], "the benchmark's length line"
    text = artifact.summary_text
    # Recent user messages first, oldest to newest, then the prefixed summary.
    assert text.index("USER: We use Postgres.") < text.index("USER: Ship Friday.")
    assert text.index("USER: Ship Friday.") < text.index(CODEX_SUMMARY_PREFIX)
    assert text.endswith(f"{CODEX_SUMMARY_PREFIX}\nProgress: chose Postgres. Next: migrate.")
    assert "Noted." not in text, "assistant turns are not kept"


async def test_codex_carries_user_messages_across_compactions_within_the_budget() -> None:
    provider = MockProvider(default="summary " * 120)
    compactor = CodexCliCompactor(provider, "m")
    first = await compactor.compact(
        CompactionRequest(cycle=0, turns=_chat("Freeze covers billing.", "OK."), token_budget=400)
    )
    second = await compactor.compact(
        CompactionRequest(
            cycle=1,
            turns=_chat("Ana owns search now.", "OK.", start=2),
            previous_artifact=first,
            token_budget=400,
        )
    )
    text = second.summary_text
    assert "USER: Freeze covers billing." in text
    assert "USER: Ana owns search now." in text
    assert text.count(CODEX_SUMMARY_PREFIX) == 1, "the old summary is not kept as a message"
    assert count_tokens(render_artifact(second)) <= 400
    assert not second.warnings, "verbatim messages only take what the summary leaves"


async def test_langchain_keeps_the_last_messages_and_summarizes_the_rest_as_xml() -> None:
    provider = MockProvider(default="## SESSION INTENT\nShip the importer.")
    compactor = LangChainSummarizationCompactor(provider, "m")
    turns = _chat(*(f"message {i} <ok>" for i in range(30)))
    artifact = await compactor.compact(CompactionRequest(cycle=0, turns=turns))

    prompt = provider.calls[0].prompt
    assert '<message type="human">message 0 &lt;ok&gt;</message>' in prompt
    assert '<message type="ai">message 1 &lt;ok&gt;</message>' in prompt
    assert "message 10 " not in prompt, "the last 20 messages are kept, not summarized"
    text = artifact.summary_text
    assert text.startswith(f"{LANGCHAIN_SUMMARY_HEADER}\n\n## SESSION INTENT")
    assert "USER: message 10 <ok>" in text
    assert "ASSISTANT: message 29 <ok>" in text


async def test_langchain_only_sends_the_last_4000_tokens_to_the_summarizer() -> None:
    provider = MockProvider(default="s")
    compactor = LangChainSummarizationCompactor(provider, "m")
    old = "Constraint: never deploy on Fridays. " + "filler " * 3000  # ~5,300 approx tokens
    turns = _chat(old, "ack", *(f"recent {i}" for i in range(22)))
    await compactor.compact(CompactionRequest(cycle=0, turns=turns))
    prompt = provider.calls[0].prompt
    assert "never deploy on Fridays" not in prompt, "LangChain's default trims it away"
    assert "filler" in prompt, "the end of the long message is kept (allow_partial)"


async def test_langchain_reads_its_previous_summary_back_as_a_message() -> None:
    provider = MockProvider(responses=["first summary", "second summary"])
    compactor = LangChainSummarizationCompactor(provider, "m")
    first = await compactor.compact(
        CompactionRequest(cycle=0, turns=_chat(*(f"a{i}" for i in range(24))), token_budget=1024)
    )
    await compactor.compact(
        CompactionRequest(
            cycle=1,
            turns=_chat(*(f"b{i}" for i in range(24)), start=24),
            previous_artifact=first,
            token_budget=1024,
        )
    )
    prompt = provider.calls[1].prompt
    assert f'<message type="human">{LANGCHAIN_SUMMARY_HEADER}\n\nfirst summary</message>' in prompt


async def test_langchain_answers_without_a_call_when_there_is_nothing_to_summarize() -> None:
    provider = MockProvider(default="unused")
    compactor = LangChainSummarizationCompactor(provider, "m")
    artifact = await compactor.compact(CompactionRequest(cycle=0, turns=_chat("hi", "hello")))
    assert not provider.calls
    assert "No previous conversation history." in artifact.summary_text


def test_trim_starts_on_a_human_message() -> None:
    turns = _chat("u" * 40, "a" * 40, "u2", "a2")
    kept = trim_last_messages(turns, 20.0)
    assert kept[0].role == TurnRole.USER
    assert [t.content for t in kept] == ["u2", "a2"]
