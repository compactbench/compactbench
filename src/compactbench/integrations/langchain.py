"""LangChain adapter.

Bridges CompactBench's :class:`~compactbench.contracts.Transcript` to and from
LangChain ``BaseMessage`` lists, and wraps any LangChain-flavoured compaction
callable as a :class:`~compactbench.compactors.Compactor` so it can be scored
against Elite practice or the hidden ranked set.

The user's compaction callable owns its own LangChain LLM — the CompactBench
``provider`` / ``model`` passed to the compactor are reserved for the downstream
target model that answers evaluation items, exactly as with the built-in
compactors.

Install the optional dependency:

    pip install 'compactbench[langchain]'

Minimum required version: ``langchain-core>=0.3``. Heavier ``langchain``
packages (``langchain``, ``langchain-openai``, etc.) are the user's choice and
are not required by this adapter.
"""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING, Any, ClassVar, TypeAlias, cast

from compactbench.compactors.base import Compactor
from compactbench.contracts import CompactionArtifact, StructuredState, Transcript
from compactbench.contracts.case import TurnRole
from compactbench.providers.base import Provider

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from langchain_core.messages import BaseMessage


_INSTALL_HINT = (
    "langchain-core is not installed. Install the LangChain integration with: "
    "pip install 'compactbench[langchain]'"
)


def _import_message_classes() -> tuple[Any, Any, Any]:
    """Return ``(SystemMessage, HumanMessage, AIMessage)`` or raise a clean ImportError.

    Returns ``Any`` because langchain_core's own stubs use loose ``dict`` types
    that would pollute strict mode throughout the module; we normalise at this
    boundary and keep the rest of the module cleanly typed.
    """
    try:
        from langchain_core.messages import (
            AIMessage,
            HumanMessage,
            SystemMessage,
        )
    except ImportError as exc:
        raise ImportError(_INSTALL_HINT) from exc
    return SystemMessage, HumanMessage, AIMessage


CompactionResult: TypeAlias = "str | list[BaseMessage] | dict[str, Any]"
"""What a LangChain-side compaction callable is allowed to return.

- ``str`` — a plain prose summary (identical treatment to ``naive-summary``)
- ``list[BaseMessage]`` — LangChain messages, concatenated into ``summary_text``
- ``dict`` — a structured shape with any of the keys ``summary_text``,
  ``structured_state``, ``selected_source_turn_ids``, ``warnings``,
  ``method_metadata``. Missing keys fall back to sensible defaults. This is
  the path for ledger / knowledge-graph style methods that want to populate
  ``StructuredState``.
"""


CompactionFn: TypeAlias = (
    "Callable[[list[BaseMessage]], "
    "CompactionResult | Awaitable[CompactionResult]]"
)


def transcript_to_messages(transcript: Transcript) -> list[BaseMessage]:
    """Convert a CompactBench :class:`Transcript` to a LangChain message list.

    Role mapping:

    - ``TurnRole.SYSTEM`` → :class:`~langchain_core.messages.SystemMessage`
    - ``TurnRole.USER`` → :class:`~langchain_core.messages.HumanMessage`
    - ``TurnRole.ASSISTANT`` → :class:`~langchain_core.messages.AIMessage`

    Turn ``id`` and ``tags`` are preserved in each message's ``additional_kwargs``
    under the keys ``compactbench_turn_id`` and ``compactbench_turn_tags`` so
    round-trip conversion preserves provenance.
    """
    system_cls, human_cls, ai_cls = _import_message_classes()
    out: list[Any] = []
    for turn in transcript.turns:
        extras: dict[str, Any] = {
            "compactbench_turn_id": turn.id,
            "compactbench_turn_tags": list(turn.tags),
        }
        match turn.role:
            case TurnRole.SYSTEM:
                out.append(system_cls(content=turn.content, additional_kwargs=extras))
            case TurnRole.USER:
                out.append(human_cls(content=turn.content, additional_kwargs=extras))
            case TurnRole.ASSISTANT:
                out.append(ai_cls(content=turn.content, additional_kwargs=extras))
    return cast("list[BaseMessage]", out)


def _message_content_as_text(message: Any) -> str:
    content: Any = message.content
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for block in cast(list[Any], content):
        if isinstance(block, str):
            parts.append(block)
            continue
        if isinstance(block, dict):
            text: Any = cast(dict[Any, Any], block).get("text")
            if isinstance(text, str):
                parts.append(text)
    return "\n".join(parts)


def _messages_to_summary(compacted: list[BaseMessage]) -> str:
    lines: list[str] = []
    for message in cast(list[Any], compacted):
        role_raw: Any = getattr(message, "type", message.__class__.__name__)
        role = str(role_raw).upper()
        text = _message_content_as_text(message)
        if text:
            lines.append(f"{role}: {text}")
    return "\n\n".join(lines)


def _selected_turn_ids(
    compacted: list[BaseMessage], source: Transcript
) -> list[int]:
    """Return the subset of source turn ids the compacted messages reference.

    If the compaction callable preserved ``compactbench_turn_id`` keys (the
    default, since :func:`transcript_to_messages` stamps every message), we
    return that set ordered. Otherwise we conservatively return every source
    turn id, signalling "whole transcript consumed".
    """
    ids: list[int] = []
    seen: set[int] = set()
    for message in cast(list[Any], compacted):
        extras = cast(dict[Any, Any], message.additional_kwargs)
        turn_id: Any = extras.get("compactbench_turn_id")
        if isinstance(turn_id, int) and turn_id not in seen:
            ids.append(turn_id)
            seen.add(turn_id)
    if not ids:
        return [turn.id for turn in source.turns]
    return sorted(ids)


def result_to_artifact(
    result: object,
    source: Transcript,
    *,
    method: str,
    version: str,
    model: str,
    provider_key: str,
    extra_metadata: dict[str, Any] | None = None,
) -> CompactionArtifact:
    """Normalise any supported ``CompactionResult`` into a validated artifact.

    ``result`` is typed ``object`` so the function can enforce the supported-type
    contract at runtime — callers can pass anything, and unsupported shapes raise
    :class:`TypeError`. Typed wrappers like :class:`LangChainCompactor` constrain
    the input via :data:`CompactionFn` at their own interface.
    """
    summary_text = ""
    structured_state = StructuredState()
    selected: list[int] = [turn.id for turn in source.turns]
    warnings: list[str] = []
    method_metadata: dict[str, Any] = {
        "method": method,
        "version": version,
        "model": model,
        "provider": provider_key,
        "adapter": "langchain",
    }
    if extra_metadata:
        method_metadata.update(extra_metadata)

    if isinstance(result, str):
        summary_text = result.strip()
    elif isinstance(result, list):
        messages = cast("list[BaseMessage]", result)
        summary_text = _messages_to_summary(messages).strip()
        selected = _selected_turn_ids(messages, source)
    elif isinstance(result, dict):
        as_dict = cast(dict[str, Any], result)
        raw_summary: Any = as_dict.get("summary_text") or as_dict.get("summary") or ""
        summary_text = str(raw_summary).strip()
        state: Any = as_dict.get("structured_state")
        if isinstance(state, StructuredState):
            structured_state = state
        elif isinstance(state, dict):
            structured_state = StructuredState.model_validate(cast(dict[str, Any], state))
        turn_ids: Any = as_dict.get("selected_source_turn_ids")
        if isinstance(turn_ids, list):
            selected = [int(cast(Any, x)) for x in cast(list[Any], turn_ids)]
        raw_warnings: Any = as_dict.get("warnings")
        if isinstance(raw_warnings, list):
            warnings = [str(cast(Any, w)) for w in cast(list[Any], raw_warnings)]
        extra: Any = as_dict.get("method_metadata")
        if isinstance(extra, dict):
            method_metadata.update(cast(dict[str, Any], extra))
    else:
        raise TypeError(
            f"LangChain compaction callable returned unsupported type {type(result).__name__}; "
            "expected str, list[BaseMessage], or dict."
        )

    return CompactionArtifact(
        summaryText=summary_text,
        structured_state=structured_state,
        selectedSourceTurnIds=selected,
        warnings=warnings,
        methodMetadata=method_metadata,
    )


class LangChainCompactor(Compactor):
    """Run any LangChain-flavoured compaction callable as a CompactBench method.

    The ``compaction_fn`` receives a ``list[BaseMessage]`` and returns one of
    :data:`CompactionResult`. Sync and async callables are both supported.

    Example — wrapping a LangChain summarisation chain::

        from langchain_openai import ChatOpenAI
        from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

        chat = ChatOpenAI(model="gpt-4o-mini", temperature=0)

        async def summarise(messages: list[BaseMessage]) -> str:
            response = await chat.ainvoke([
                SystemMessage(content="Summarise the conversation, preserving every "
                                       "constraint, decision, and unresolved task."),
                HumanMessage(content="\\n".join(str(m.content) for m in messages)),
            ])
            return str(response.content)

        compactor = LangChainCompactor(
            provider=target_provider,  # e.g. GroqProvider() — answers eval items
            model="llama-3.3-70b-versatile",
            compaction_fn=summarise,
            method_name="my-langchain-summary",
            method_version="0.1.0",
        )

    The CompactBench ``provider`` and ``model`` are used by the runner when it
    queries the target model for evaluation-item responses, *not* by your
    compaction function — your function owns its own LangChain LLM. This
    mirrors how a production LangChain app typically has a summariser LLM
    separate from the main chat model.
    """

    name: ClassVar[str] = "langchain"
    version: ClassVar[str] = "0.1.0"

    def __init__(
        self,
        provider: Provider,
        model: str,
        *,
        compaction_fn: CompactionFn,
        method_name: str | None = None,
        method_version: str | None = None,
        extra_metadata: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(provider, model)
        # Fail fast with a helpful error if langchain-core isn't installed.
        _import_message_classes()
        self._compaction_fn = compaction_fn
        self._method_name = method_name or "langchain-custom"
        self._method_version = method_version or self.version
        self._extra_metadata = extra_metadata

    async def compact(
        self,
        transcript: Transcript,
        config: dict[str, Any] | None = None,
        previous_artifact: CompactionArtifact | None = None,
    ) -> CompactionArtifact:
        messages = transcript_to_messages(transcript)
        raw: Any = self._compaction_fn(messages)
        if inspect.isawaitable(raw):
            raw = await raw
        result: CompactionResult = cast(CompactionResult, raw)
        return result_to_artifact(
            result,
            transcript,
            method=self._method_name,
            version=self._method_version,
            model=self.model,
            provider_key=self.provider.key,
            extra_metadata=self._extra_metadata,
        )


__all__ = [
    "CompactionFn",
    "CompactionResult",
    "LangChainCompactor",
    "result_to_artifact",
    "transcript_to_messages",
]
