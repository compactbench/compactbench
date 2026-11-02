# Integrations

CompactBench's `Compactor` ABC works standalone, but most production code already lives inside a framework. The `compactbench.integrations` package ships thin adapters that let you benchmark what you already have.

- [LangChain](#langchain) — wrap any callable that takes `list[BaseMessage]`
- [LlamaIndex](#llamaindex) — wrap any callable that takes `list[ChatMessage]`

Both adapters share the same return-shape contract (`str | list[messages] | dict`) and preserve turn provenance via `additional_kwargs` so filtered-message methods automatically populate `CompactionArtifact.selected_source_turn_ids`.

**What your callable receives.** At the first compaction, the whole opening conversation.
At every later compaction, a system message holding your previous artifact
(`"Summary of the conversation so far: …"`, marked `compactbench_previous_artifact` in
`additional_kwargs`) followed by only the turns since then — the same shape a framework
app sees after its own summarisation step. Tool output arrives as user messages prefixed
`TOOL[name]:`.

**`provider` / `model`.** Your callable owns its own LLM, so these are only recorded as the
method's model. The reader that answers the questions is set on the run
(`--reader-provider` / `--reader-model`).

## LangChain

`compactbench.integrations.langchain` wraps any LangChain-flavoured compaction callable as a CompactBench [`Compactor`](writing-a-compactor.md) so it can be scored against the Practice suite or the hidden Elite set.

**Install:**

```bash
pip install 'compactbench[langchain]'
```

That adds only `langchain-core>=0.3`. Bring your own `langchain`, `langchain-openai`, `langchain-anthropic`, etc. — they're all compatible.

### Wrap a summarisation chain

```python
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from compactbench.integrations.langchain import LangChainCompactor
from compactbench.providers import MockProvider

summariser = ChatOpenAI(model="gpt-4o-mini", temperature=0)


async def summarise(messages: list[BaseMessage]) -> str:
    response = await summariser.ainvoke(
        [
            SystemMessage(
                content=(
                    "Summarise the conversation, preserving every constraint, "
                    "decision, and unresolved task. Reply with the summary only."
                )
            ),
            *messages,
        ]
    )
    return str(response.content)


compactor = LangChainCompactor(
    # Your callable owns its LLM; provider/model are only recorded as the
    # method's model. The reader is configured on the run.
    provider=MockProvider(),
    model="gpt-4o-mini",
    compaction_fn=summarise,
    method_name="openai-mini-summary",
    method_version="0.1.0",
)
```

Hand `compactor` to `compactbench run --method …` (via a custom wrapper) or use the runner API directly. The full submission flow is the same as for any other method: see [submitting](submitting.md).

### Return structured state

If your method populates ledgers or extracted entities, return a dict instead of a string:

```python
async def structured(messages: list[BaseMessage]) -> dict:
    # ... your pipeline ...
    return {
        "summary_text": prose_summary,
        "structured_state": {
            "locked_decisions": ["supplier list must be EU-only"],
            "forbidden_behaviors": ["recommending non-EU suppliers"],
            "immutable_facts": [...],
            "entity_map": {"Alice": "owner of task A", "Bob": "owner of task B"},
            "unresolved_items": [...],
        },
        "warnings": ["truncated two early turns"],
        "method_metadata": {"chain_type": "summary_memory", "calls": 3},
    }
```

The dict keys are optional — missing keys fall back to sensible defaults. `summary` is accepted as an alias for `summary_text` so you can return `ConversationSummaryMemory.predict_new_summary(...)` output directly.

### Preserving turn provenance

`request_to_messages` (via `transcript_to_messages`) stamps each LangChain message with
`additional_kwargs["compactbench_turn_id"]`. If your callable returns a filtered
`list[BaseMessage]`, the adapter reads those ids back and populates
`CompactionArtifact.selected_source_turn_ids` automatically — useful for
`trim_messages`-style retention methods and for the contradiction scorer.

```python
from langchain_core.messages.utils import trim_messages


def trim(messages: list[BaseMessage]) -> list[BaseMessage]:
    return trim_messages(
        messages,
        max_tokens=500,
        token_counter=len,  # swap for a real tokenizer
        strategy="last",
    )


compactor = LangChainCompactor(
    provider=MockProvider(),
    model="none",
    compaction_fn=trim,
    method_name="trim-last-500",
)
```

### Benchmarking legacy `ConversationSummaryMemory`

The legacy `langchain.memory.ConversationSummaryMemory` API predates `langchain-core`'s message primitives but still works if you have it installed. Wrap it like this:

```python
from langchain.memory import ConversationSummaryMemory
from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage

memory = ConversationSummaryMemory(llm=ChatOpenAI(model="gpt-4o-mini"))


def compact_with_legacy_memory(messages: list[BaseMessage]) -> str:
    # ConversationSummaryMemory consumes messages in (human, ai) pairs.
    human: str | None = None
    for message in messages:
        if message.type == "human":
            human = str(message.content)
        elif message.type == "ai" and human is not None:
            memory.save_context({"input": human}, {"output": str(message.content)})
            human = None
    return memory.buffer  # the running summary string
```

This is exactly the shape a production LangChain app uses — now it's a row on the CompactBench leaderboard.

## LlamaIndex

`compactbench.integrations.llamaindex` mirrors the LangChain adapter — same three public symbols, same three supported return shapes (`str | list[ChatMessage] | dict`), same provenance-preserving `additional_kwargs`. Pick whichever framework you already have in production.

**Install:**

```bash
pip install 'compactbench[llamaindex]'
```

That adds only `llama-index-core>=0.11`. Your LLM binding (`llama-index-llms-openai`, `llama-index-llms-ollama`, etc.) stays your choice.

### Wrap a `ChatSummaryMemoryBuffer`

```python
from llama_index.core.base.llms.types import ChatMessage
from llama_index.core.memory import ChatSummaryMemoryBuffer
from llama_index.llms.openai import OpenAI

from compactbench.integrations.llamaindex import LlamaIndexCompactor
from compactbench.providers import MockProvider

summariser_llm = OpenAI(model="gpt-4o-mini", temperature=0)


def summarise(messages: list[ChatMessage]) -> str:
    memory = ChatSummaryMemoryBuffer.from_defaults(llm=summariser_llm, token_limit=500)
    memory.set(messages)
    return "\n".join(str(m.content) for m in memory.get())


compactor = LlamaIndexCompactor(
    provider=MockProvider(),  # unused: your callable owns its LLM
    model="gpt-4o-mini",
    compaction_fn=summarise,
    method_name="llamaindex-chat-summary-buffer",
    method_version="0.1.0",
)
```

### Return structured state

Same dict-shape contract as the LangChain adapter — return any of `summary_text`, `structured_state`, `selected_source_turn_ids`, `warnings`, `method_metadata`:

```python
async def structured(messages: list[ChatMessage]) -> dict:
    # ... your pipeline ...
    return {
        "summary_text": prose_summary,
        "structured_state": {
            "locked_decisions": [...],
            "forbidden_behaviors": [...],
            "entity_map": {...},
        },
        "method_metadata": {"memory_type": "chat_summary_buffer", "calls": 3},
    }
```

### Preserving turn provenance

`request_to_chat_messages` (via `transcript_to_chat_messages`) stamps `additional_kwargs["compactbench_turn_id"]` on every outgoing message. If your callable returns a filtered `list[ChatMessage]`, the adapter reads those ids back and populates `CompactionArtifact.selected_source_turn_ids` automatically.

```python
def keep_last_n(messages: list[ChatMessage], n: int = 6) -> list[ChatMessage]:
    return messages[-n:]


compactor = LlamaIndexCompactor(
    provider=MockProvider(),
    model="none",
    compaction_fn=lambda ms: keep_last_n(ms, 6),
    method_name="keep-last-6",
)
```

## Other frameworks

**CrewAI** and **Haystack** adapters follow the same shape (`result_to_artifact` + a subclass of `Compactor`). Open a [GitHub issue](https://github.com/compactbench/compactbench/issues/new) if you want a specific framework prioritised — or send a PR; the LangChain and LlamaIndex adapters at `src/compactbench/integrations/` are good reference templates.
