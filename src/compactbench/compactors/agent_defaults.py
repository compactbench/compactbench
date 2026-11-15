"""Agents' default compaction, reproduced from their open-source code.

Each adapter copies an agent's own compaction prompt and the shape of what it keeps
after compacting, so CompactBench can measure what that agent forgets with its
out-of-the-box settings. Only agents whose compaction code is open source are
reproduced, at a pinned commit; see ``THIRD_PARTY_NOTICES.md``.

Two things are adapted, the same way for every adapter:

- **The budget.** The agents keep some recent messages verbatim next to the summary
  (Codex CLI up to 20,000 tokens of user messages, LangChain the last 20 messages).
  Under a token budget, verbatim messages get at most a quarter of it, newest first,
  and the summary the rest; the benchmark's standard length line is appended to the
  agent's prompt, as it is for every built-in. Without a budget, the agent's own
  limits apply.
- **The transcript.** Turns are passed as plain text in one request, where the agent
  would send them as chat messages.
"""

from __future__ import annotations

import re
from typing import ClassVar
from xml.sax.saxutils import escape, quoteattr

from compactbench.compactors._utils import (
    budget_instruction,
    finalize,
    fit_summary_text,
    output_tokens,
    reasoning_effort,
)
from compactbench.compactors.base import Compactor
from compactbench.contracts import CompactionArtifact, CompactionRequest, StructuredState, Turn
from compactbench.contracts.case import TurnRole
from compactbench.providers import CompletionRequest
from compactbench.rendering import render_request, render_turn
from compactbench.tokens import count_tokens

#: Share of the budget that verbatim messages may use; the summary gets the rest.
VERBATIM_SHARE = 0.25

# --- Codex CLI -------------------------------------------------------------------
# openai/codex @ a394ff9cf66e9c17258077e8f8295178ca0c2025, Apache-2.0.
# codex-rs/prompts/templates/compact/prompt.md and summary_prefix.md; behaviour from
# codex-rs/core/src/compact.rs (local compaction): the prompt is sent as a user message
# after the whole history; the new history is the most recent user messages (up to
# COMPACT_USER_MESSAGE_MAX_TOKENS = 20,000) followed by SUMMARY_PREFIX + "\n" + summary.

CODEX_PROMPT = """You are performing a CONTEXT CHECKPOINT COMPACTION. Create a handoff summary for another LLM that will resume the task.

Include:
- Current progress and key decisions made
- Important context, constraints, or user preferences
- What remains to be done (clear next steps)
- Any critical data, examples, or references needed to continue

Be concise, structured, and focused on helping the next LLM seamlessly continue the work."""

CODEX_SUMMARY_PREFIX = "Another language model started to solve this problem and produced a summary of its thinking process. You also have access to the state of the tools that were used by that language model. Use this to build on the work that has already been done and avoid duplicating work. Here is the summary produced by the other language model, use the information in this summary to assist with your own analysis:"

CODEX_USER_MESSAGE_MAX_TOKENS = 20_000

# --- LangChain SummarizationMiddleware --------------------------------------------
# langchain-ai/langchain @ 2529c2d1f2f98c7467e02ade9edcd21c80a9c34e, MIT.
# libs/langchain_v1/langchain/agents/middleware/summarization.py: DEFAULT_SUMMARY_PROMPT,
# keep the last 20 messages, summarize the rest after trimming it to its last 4,000
# tokens (count_tokens_approximately: 4 characters a token, 3 tokens a message), and
# replace them with one human message "Here is a summary of the conversation to date".
# Messages are serialized with langchain_core's get_buffer_string(format="xml").

LANGCHAIN_PROMPT = """<role>
Context Extraction Assistant
</role>

<primary_objective>
Your sole objective in this task is to extract the highest quality/most relevant context from the conversation history below.
</primary_objective>

<objective_information>
You're nearing the total number of input tokens you can accept, so you must extract the highest quality/most relevant pieces of information from your conversation history.
This context will then overwrite the conversation history presented below. Because of this, ensure the context you extract is only the most important information to continue working toward your overall goal.
</objective_information>

<instructions>
The conversation history below will be replaced with the context you extract in this step.
You want to ensure that you don't repeat any actions you've already completed, so the context you extract from the conversation history should be focused on the most important information to your overall goal.

You should structure your summary using the following sections. Each section acts as a checklist - you must populate it with relevant information or explicitly state "None" if there is nothing to report for that section:

## SESSION INTENT

What is the user's primary goal or request? What overall task are you trying to accomplish? This should be concise but complete enough to understand the purpose of the entire session.

## SUMMARY

Extract and record all of the most important context from the conversation history. Include important choices, conclusions, or strategies determined during this conversation. Include the reasoning behind key decisions. Document any rejected options and why they were not pursued.

## ARTIFACTS

What artifacts, files, or resources were created, modified, or accessed during this conversation? For file modifications, list specific file paths and briefly describe the changes made to each. This section prevents silent loss of artifact information.

## NEXT STEPS

What specific tasks remain to be completed to achieve the session intent? What should you do next?

</instructions>

The user will message you with the full message history from which you'll extract context to create a replacement. Carefully read through it all and think deeply about what information is most important to your overall goal and should be saved:

With all of this in mind, please carefully read over the entire conversation history, and extract the most important and relevant context to replace it so that you can free up space in the conversation history.
Respond ONLY with the extracted context. Do not include any additional information, or text before or after the extracted context.

<messages>
Messages to summarize:
{messages}
</messages>"""

LANGCHAIN_SUMMARY_HEADER = "Here is a summary of the conversation to date:"
LANGCHAIN_MESSAGES_TO_KEEP = 20
LANGCHAIN_TRIM_TOKENS = 4_000

# Our own separator between the summary and the verbatim messages in an artifact, so
# the next cycle can tell them apart again.
_RECENT = "RECENT MESSAGES:"
_TURN_START = re.compile(r"\n\n(?=(?:USER|ASSISTANT|SYSTEM|TOOL(?:\[[^\]\n]*\])?): )")
_LABEL = re.compile(r"^(USER|ASSISTANT|SYSTEM|TOOL)(?:\[([^\]\n]*)\])?: ", re.S)


def _parse_turns(text: str) -> list[Turn]:
    """Turns this module rendered with :func:`render_turn`, read back."""
    turns: list[Turn] = []
    for block in _TURN_START.split(text.strip()):
        match = _LABEL.match(block)
        if match is None:
            continue
        turns.append(
            Turn(
                id=len(turns),
                role=TurnRole(match.group(1).lower()),
                content=block[match.end() :],
                name=match.group(2),
            )
        )
    return turns


def _newest_that_fit(turns: list[Turn], tokens: int, *, count: int | None = None) -> list[Turn]:
    """The most recent ``turns`` (at most ``count``) whose rendering fits ``tokens``."""
    kept: list[Turn] = []
    used = 0
    for turn in reversed(turns):
        if count is not None and len(kept) >= count:
            break
        cost = count_tokens(render_turn(turn)) + 2
        if used + cost > tokens:
            break
        kept.append(turn)
        used += cost
    return list(reversed(kept))


def _artifact(
    compactor: Compactor,
    request: CompactionRequest,
    text: str,
    *,
    calls: int,
    prompt_tokens: int,
    completion_tokens: int,
) -> CompactionArtifact:
    summary, warnings = fit_summary_text(text)
    artifact = CompactionArtifact(
        summaryText=summary,
        structured_state=StructuredState(),
        selectedSourceTurnIds=[t.id for t in request.turns],
        warnings=warnings,
        methodMetadata={
            "method": compactor.name,
            "version": compactor.version,
            "model": compactor.model,
            "provider": compactor.provider.key,
            "calls": calls,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
        },
    )
    return finalize(artifact, request)


class CodexCliCompactor(Compactor):
    """Codex CLI's local compaction: its handoff-summary prompt after the history, then the
    most recent user messages kept verbatim ahead of the prefixed summary."""

    name: ClassVar[str] = "codex-cli"
    version: ClassVar[str] = "1.0.0"

    async def compact(self, request: CompactionRequest) -> CompactionArtifact:
        budget = request.token_budget
        length = f"\n\n{budget_instruction(request, share=1 - VERBATIM_SHARE)}" if budget else ""
        response = await self.provider.complete(
            CompletionRequest(
                model=self.model,
                prompt=f"{render_request(request)}\n\nUSER: {CODEX_PROMPT}{length}",
                max_tokens=output_tokens(request),
                reasoning_effort=reasoning_effort(self.config),
            )
        )
        summary_message = f"{CODEX_SUMMARY_PREFIX}\n{response.text.strip()}"

        # Codex keeps user messages from the whole history; earlier cycles' are in the
        # previous artifact, ahead of its summary.
        users: list[Turn] = []
        if request.previous_artifact is not None:
            head = request.previous_artifact.summary_text.partition(CODEX_SUMMARY_PREFIX)[0]
            users = [t for t in _parse_turns(head) if t.role == TurnRole.USER]
        users += [t for t in request.turns if t.role == TurnRole.USER]
        room = (
            max(0, budget - count_tokens(f"SUMMARY:\n{summary_message}") - 4)
            if budget
            else CODEX_USER_MESSAGE_MAX_TOKENS
        )
        kept = _newest_that_fit(users, room)
        text = "\n\n".join([*(render_turn(t) for t in kept), summary_message])
        return _artifact(
            self,
            request,
            text,
            calls=1,
            prompt_tokens=response.prompt_tokens,
            completion_tokens=response.completion_tokens,
        )


def _xml(turns: list[Turn]) -> str:
    """langchain_core ``get_buffer_string(format="xml")`` for these turns."""
    kinds = {
        TurnRole.USER: "human",
        TurnRole.ASSISTANT: "ai",
        TurnRole.SYSTEM: "system",
        TurnRole.TOOL: "tool",
    }
    return "\n".join(
        f"<message type={quoteattr(kinds[t.role])}>{escape(t.content)}</message>" for t in turns
    )


def _approx_tokens(turn: Turn) -> float:
    """langchain_core ``count_tokens_approximately`` for one message."""
    return len(turn.content) / 4.0 + 3.0


def trim_last_messages(turns: list[Turn], limit: float) -> list[Turn]:
    """``trim_messages(strategy="last", start_on="human", allow_partial=True)``: the most
    recent messages within ``limit``, the oldest of them cut from its start if needed,
    starting on a human message."""
    kept: list[Turn] = []
    used = 0.0
    for turn in reversed(turns):
        cost = _approx_tokens(turn)
        if used + cost <= limit:
            kept.append(turn)
            used += cost
            continue
        room = int((limit - used - 3.0) * 4)
        if room > 0:
            kept.append(turn.model_copy(update={"content": turn.content[-room:]}))
        break
    kept.reverse()
    while kept and kept[0].role != TurnRole.USER:
        kept.pop(0)
    return kept


class LangChainSummarizationCompactor(Compactor):
    """LangChain's ``SummarizationMiddleware`` with its defaults: summarize all but the
    last 20 messages (only their last ~4,000 tokens reach the summarizer) and keep the
    20 verbatim after the summary."""

    name: ClassVar[str] = "langchain-summarization"
    version: ClassVar[str] = "1.0.0"

    async def compact(self, request: CompactionRequest) -> CompactionArtifact:
        budget = request.token_budget
        history: list[Turn] = []
        previous = request.previous_artifact
        if previous is not None:
            summary_part, _, recent = previous.summary_text.partition(f"\n\n{_RECENT}\n")
            history.append(Turn(id=0, role=TurnRole.USER, content=summary_part.strip()))
            history += _parse_turns(recent)
        history += list(request.turns)

        if budget:
            kept = _newest_that_fit(
                history, int(budget * VERBATIM_SHARE), count=LANGCHAIN_MESSAGES_TO_KEEP
            )
        else:
            kept = history[-LANGCHAIN_MESSAGES_TO_KEEP:]
        to_summarize = history[: len(history) - len(kept)]
        trimmed = trim_last_messages(to_summarize, LANGCHAIN_TRIM_TOKENS)

        calls = prompt_tokens = completion_tokens = 0
        # LangChain's own answers when there is nothing (left) to summarize; no model call.
        if not to_summarize:
            summary = "No previous conversation history."
        elif not trimmed:
            summary = "Previous conversation was too long to summarize."
        else:
            prompt = LANGCHAIN_PROMPT.replace("{messages}", _xml(trimmed)).rstrip()
            if budget:
                prompt += f"\n\n{budget_instruction(request, share=1 - VERBATIM_SHARE)}"
            response = await self.provider.complete(
                CompletionRequest(
                    model=self.model,
                    prompt=prompt,
                    max_tokens=output_tokens(request),
                    reasoning_effort=reasoning_effort(self.config),
                )
            )
            summary = response.text.strip()
            calls, prompt_tokens = 1, response.prompt_tokens
            completion_tokens = response.completion_tokens
        text = f"{LANGCHAIN_SUMMARY_HEADER}\n\n{summary}"
        if kept:
            text += f"\n\n{_RECENT}\n" + "\n\n".join(render_turn(t) for t in kept)
        return _artifact(
            self,
            request,
            text,
            calls=calls,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
