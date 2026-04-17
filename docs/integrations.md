# Integrations

CompactBench's `Compactor` ABC works standalone, but most production code already lives inside a framework. The `compactbench.integrations` package ships thin adapters that let you benchmark what you already have.

## LangChain

`compactbench.integrations.langchain` wraps any LangChain-flavoured compaction callable as a CompactBench [`Compactor`](writing-a-compactor.md) so it can be scored against Elite practice or the hidden ranked set.

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
from compactbench.providers import GroqProvider

summariser = ChatOpenAI(model="gpt-4o-mini", temperature=0)

async def summarise(messages: list[BaseMessage]) -> str:
    response = await summariser.ainvoke([
        SystemMessage(content=(
            "Summarise the conversation, preserving every constraint, "
            "decision, and unresolved task. Reply with the summary only."
        )),
        *messages,
    ])
    return str(response.content)

compactor = LangChainCompactor(
    # The CompactBench provider + model are for the *target* model that
    # answers evaluation items — not for your summariser. Your callable
    # owns its own LangChain LLM.
    provider=GroqProvider(),
    model="llama-3.3-70b-versatile",
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

`transcript_to_messages` stamps each LangChain message with
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
    provider=GroqProvider(),
    model="llama-3.3-70b-versatile",
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

## Other frameworks

Adapters for **LlamaIndex** and **CrewAI** are on the roadmap and will follow the same shape (`result_to_artifact` + a subclass of `Compactor`). Open a [GitHub issue](https://github.com/compactbench/compactbench/issues/new) if you want a specific framework prioritised — or send a PR; the LangChain adapter at `src/compactbench/integrations/langchain.py` is a good reference template.
