"""LlamaIndex adapter.

Bridges CompactBench's :class:`~compactbench.contracts.Transcript` to and from
LlamaIndex ``ChatMessage`` lists, and wraps any LlamaIndex-flavoured compaction
callable as a :class:`~compactbench.compactors.Compactor`.

Like the LangChain adapter, the user's callable owns its own LlamaIndex LLM —
the CompactBench ``provider`` / ``model`` passed to the compactor are reserved
for the downstream target model that answers evaluation items.

Install the optional dependency:

    pip install 'compactbench[llamaindex]'

Minimum required version: ``llama-index-core>=0.11``. Heavier LlamaIndex
packages (``llama-index``, ``llama-index-llms-openai``, ``llama-index-memory-*``,
etc.) are the user's choice and are not required by this adapter.
"""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING, Any, ClassVar, TypeAlias, cast

from compactbench.compactors.base import Compactor
from compactbench.contracts import (
    CompactionArtifact,
    CompactionRequest,
    StructuredState,
    Transcript,
)
from compactbench.contracts.case import TurnRole
from compactbench.providers.base import Provider
from compactbench.rendering import render_artifact

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from llama_index.core.base.llms.types import ChatMessage


_INSTALL_HINT = (
    "llama-index-core is not installed. Install the LlamaIndex integration with: "
    "pip install 'compactbench[llamaindex]'"
)


def _import_chat_types() -> tuple[Any, Any]:
    """Return ``(ChatMessage, MessageRole)`` or raise a clean ImportError.

    Returns ``Any`` because llama-index-core's types use dict-typed attributes
    under the hood; we normalise at this boundary and keep the rest of the
    module cleanly typed.
    """
    try:
        from llama_index.core.base.llms.types import ChatMessage, MessageRole
    except ImportError as exc:
        raise ImportError(_INSTALL_HINT) from exc
    return ChatMessage, MessageRole


CompactionResult: TypeAlias = "str | list[ChatMessage] | dict[str, Any]"
"""What a LlamaIndex-side compaction callable is allowed to return.

- ``str`` — a plain prose summary (identical treatment to ``naive-summary``)
- ``list[ChatMessage]`` — LlamaIndex messages, concatenated into ``summary_text``
- ``dict`` — a structured shape with any of the keys ``summary_text``,
  ``structured_state``, ``selected_source_turn_ids``, ``warnings``,
  ``method_metadata``. Missing keys fall back to sensible defaults. This is
  the path for methods that want to populate ``StructuredState``.
"""


CompactionFn: TypeAlias = (
    "Callable[[list[ChatMessage]], CompactionResult | Awaitable[CompactionResult]]"
)


_ROLE_NAMES = {
    TurnRole.SYSTEM: "system",
    TurnRole.USER: "user",
    TurnRole.ASSISTANT: "assistant",
    # Tool output becomes a user message: a bare TOOL-role message without the
    # tool call that produced it breaks many LlamaIndex memory buffers.
    TurnRole.TOOL: "user",
}


def transcript_to_chat_messages(transcript: Transcript) -> list[ChatMessage]:
    """Convert a CompactBench :class:`Transcript` to a LlamaIndex ``ChatMessage`` list.

    Role mapping:

    - ``TurnRole.SYSTEM`` → ``MessageRole.SYSTEM``
    - ``TurnRole.USER`` → ``MessageRole.USER``
    - ``TurnRole.ASSISTANT`` → ``MessageRole.ASSISTANT``

    Turn ``id`` and ``tags`` are preserved in each message's ``additional_kwargs``
    under the keys ``compactbench_turn_id`` and ``compactbench_turn_tags`` so
    round-trip conversion preserves provenance.
    """
    chat_message_cls, role_cls = _import_chat_types()
    out: list[Any] = []
    for turn in transcript.turns:
        extras: dict[str, Any] = {
            "compactbench_turn_id": turn.id,
            "compactbench_turn_tags": list(turn.tags),
        }
        role = getattr(role_cls, _ROLE_NAMES[turn.role].upper())
        content = turn.content
        if turn.role == TurnRole.TOOL:
            content = f"{f'TOOL[{turn.name}]' if turn.name else 'TOOL'}: {content}"
        out.append(chat_message_cls(role=role, content=content, additional_kwargs=extras))
    return cast("list[ChatMessage]", out)


def request_to_chat_messages(request: CompactionRequest) -> list[ChatMessage]:
    """Convert a :class:`CompactionRequest` to LlamaIndex ``ChatMessage`` objects.

    From the second cycle on, the previous artifact comes first as a system
    message (marked ``compactbench_previous_artifact`` in ``additional_kwargs``),
    followed by the turns since that compaction.
    """
    chat_message_cls, role_cls = _import_chat_types()
    messages: list[Any] = []
    if request.previous_artifact is not None:
        messages.append(
            chat_message_cls(
                role=role_cls.SYSTEM,
                content="Summary of the conversation so far:\n"
                + (render_artifact(request.previous_artifact) or "(empty)"),
                additional_kwargs={"compactbench_previous_artifact": True},
            )
        )
    messages.extend(transcript_to_chat_messages(Transcript(turns=list(request.turns))))
    return cast("list[ChatMessage]", messages)


def _message_content_as_text(message: Any) -> str:
    """Extract plain text from a ``ChatMessage``'s content field.

    Handles the three shapes LlamaIndex 0.11+ supports: ``str``, ``None``, and
    ``list[ContentBlock]`` where content blocks may expose ``.text`` or may be
    ``TextBlock``-like dict mappings.
    """
    content: Any = message.content
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for block in cast(list[Any], content):
        if isinstance(block, str):
            parts.append(block)
            continue
        text_attr: Any = getattr(block, "text", None)
        if isinstance(text_attr, str):
            parts.append(text_attr)
            continue
        if isinstance(block, dict):
            text_val: Any = cast(dict[Any, Any], block).get("text")
            if isinstance(text_val, str):
                parts.append(text_val)
    return "\n".join(parts)


def _messages_to_summary(compacted: list[ChatMessage]) -> str:
    lines: list[str] = []
    for message in cast(list[Any], compacted):
        role_raw: Any = getattr(message, "role", "UNKNOWN")
        role_name: Any = (
            getattr(role_raw, "value", None) or getattr(role_raw, "name", None) or str(role_raw)
        )
        text = _message_content_as_text(message)
        if text:
            lines.append(f"{str(role_name).upper()}: {text}")
    return "\n\n".join(lines)


def _selected_turn_ids(compacted: list[ChatMessage], source: Transcript) -> list[int]:
    """Return the subset of source turn ids the compacted messages reference.

    If the compaction callable preserved ``compactbench_turn_id`` keys, we
    return that set ordered. Otherwise we conservatively return every source
    turn id, signalling "whole transcript consumed".
    """
    ids: list[int] = []
    seen: set[int] = set()
    for message in cast(list[Any], compacted):
        extras_raw: Any = getattr(message, "additional_kwargs", None)
        if not isinstance(extras_raw, dict):
            continue
        extras = cast(dict[Any, Any], extras_raw)
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
    :class:`TypeError`. Typed wrappers like :class:`LlamaIndexCompactor` constrain
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
        "adapter": "llamaindex",
    }
    if extra_metadata:
        method_metadata.update(extra_metadata)

    if isinstance(result, str):
        summary_text = result.strip()
    elif isinstance(result, list):
        messages = cast("list[ChatMessage]", result)
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
            ids_list: list[Any] = cast(list[Any], turn_ids)
            selected = [int(x) for x in ids_list]
        raw_warnings: Any = as_dict.get("warnings")
        if isinstance(raw_warnings, list):
            warnings_list: list[Any] = cast(list[Any], raw_warnings)
            warnings = [str(w) for w in warnings_list]
        extra: Any = as_dict.get("method_metadata")
        if isinstance(extra, dict):
            method_metadata.update(cast(dict[str, Any], extra))
    else:
        raise TypeError(
            f"LlamaIndex compaction callable returned unsupported type {type(result).__name__}; "
            "expected str, list[ChatMessage], or dict."
        )

    return CompactionArtifact(
        summaryText=summary_text,
        structured_state=structured_state,
        selectedSourceTurnIds=selected,
        warnings=warnings,
        methodMetadata=method_metadata,
    )


class LlamaIndexCompactor(Compactor):
    """Run any LlamaIndex-flavoured compaction callable as a CompactBench method.

    The ``compaction_fn`` receives a ``list[ChatMessage]`` and returns one of
    :data:`CompactionResult`. Sync and async callables are both supported.

    Example — wrapping a LlamaIndex ``ChatSummaryMemoryBuffer``::

        from llama_index.core.memory import ChatSummaryMemoryBuffer
        from llama_index.core.base.llms.types import ChatMessage
        from llama_index.llms.openai import OpenAI

        llm = OpenAI(model="gpt-4o-mini", temperature=0)

        def summarise(messages: list[ChatMessage]) -> str:
            memory = ChatSummaryMemoryBuffer.from_defaults(llm=llm, token_limit=500)
            memory.set(messages)
            return "\\n".join(str(m.content) for m in memory.get())

        compactor = LlamaIndexCompactor(
            provider=MockProvider(),  # unused: your function owns its LLM
            model="gpt-4o-mini",  # recorded as the method's model
            compaction_fn=summarise,
            method_name="llamaindex-chat-summary-buffer",
            method_version="0.1.0",
        )

    Your function owns its own LlamaIndex LLM; ``provider`` / ``model`` are only
    recorded as the method's model. The reader that answers the probes is
    configured separately on the run. From the second cycle on, the messages
    start with the previous artifact as a system message — see
    :func:`request_to_chat_messages`.
    """

    name: ClassVar[str] = "llamaindex"
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
        # Fail fast with a helpful error if llama-index-core isn't installed.
        _import_chat_types()
        self._compaction_fn = compaction_fn
        self._method_name = method_name or "llamaindex-custom"
        self._method_version = method_version or self.version
        self._extra_metadata = extra_metadata

    async def compact(self, request: CompactionRequest) -> CompactionArtifact:
        messages = request_to_chat_messages(request)
        raw: Any = self._compaction_fn(messages)
        if inspect.isawaitable(raw):
            raw = await raw
        result: CompactionResult = cast(CompactionResult, raw)
        return result_to_artifact(
            result,
            Transcript(turns=list(request.turns)),
            method=self._method_name,
            version=self._method_version,
            model=self.model,
            provider_key=self.provider.key,
            extra_metadata=self._extra_metadata,
        )


__all__ = [
    "CompactionFn",
    "CompactionResult",
    "LlamaIndexCompactor",
    "request_to_chat_messages",
    "result_to_artifact",
    "transcript_to_chat_messages",
]
