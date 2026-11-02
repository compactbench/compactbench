# Writing a compactor

A compactor is one class with one async method. It receives a `CompactionRequest` and
returns a `CompactionArtifact`.

```python
from typing import ClassVar

from compactbench.compactors import Compactor
from compactbench.contracts import CompactionArtifact, CompactionRequest
from compactbench.providers import CompletionRequest
from compactbench.rendering import render_request


class MyCompactor(Compactor):
    name: ClassVar[str] = "my-method"
    version: ClassVar[str] = "0.1.0"

    async def compact(self, request: CompactionRequest) -> CompactionArtifact:
        response = await self.provider.complete(
            CompletionRequest(
                model=self.model,
                prompt="Update the running summary:\n\n" + render_request(request),
                max_tokens=8_000,  # room for thinking on reasoning models
                reasoning_effort="low",
            )
        )
        return CompactionArtifact(summaryText=response.text.strip())
```

Run it:

```bash
compactbench run --method path/to/my_compactor.py:MyCompactor \
                 --suite practice --provider anthropic --model claude-haiku-5-5 --controls
```

## What the request holds

| Field | Cycle 0 | Later cycles |
|---|---|---|
| `cycle` | `0` | `1, 2, …` |
| `turns` | the whole opening conversation | **only** the turns since your last compaction |
| `previous_artifact` | `None` | exactly what you returned last cycle |
| `token_budget` | the run's budget (or `None`) | same |

The earlier turns are never sent again. Anything your artifact dropped is gone — that is
the point of the drift cycles.

Turns have a `role` (`user`, `assistant`, `system`, `tool`), `content`, and for tool output
a `name` (`read_file`, `run_tests`, …). `compactbench.rendering.render_request` renders a
request as one prompt body; `render_artifact` shows exactly what the reader will see.

## The artifact

```python
CompactionArtifact(
    summaryText="...",  # free text
    structured_state=StructuredState(  # optional sections
        immutable_facts=[...],
        locked_decisions=[...],
        forbidden_behaviors=[...],
        deferred_items=[...],
        unresolved_items=[...],
        entity_map={"Dana Whitfield": "owns the export job"},
    ),
    methodMetadata={...},  # carried to your next cycle, never shown to the reader
)
```

The reader sees `render_artifact(artifact)`: the summary, then each non-empty section. The
token budget is measured on that rendering, so moving text into `structured_state` doesn't
avoid it. An over-budget artifact is cut before the reader sees it, and disqualifies a
ranked run, so models that overshoot a word limit need a safety net:
`compactbench.compactors.fit_to_budget(artifact, request.token_budget)` returns the
artifact trimmed to fit (oldest structured entries first, then the end of the summary),
as the built-in methods do. `methodMetadata` is a good place for state you want back next
cycle (the `truncate-last-n` control keeps its turns there).

## The model your method uses

`self.provider` and `self.model` are the method's own model — whatever `--provider` /
`--model` the run was given. The reader that answers the probes is configured separately
(`--reader-provider` / `--reader-model`, or pinned by a season), so your method can use any
model you like, or none.

Method-specific settings arrive as `self.config`: the JSON object you give with
`--method-config` locally, or in the "Method config" field when you submit.

## Check before you submit

```bash
compactbench run --method my_compactor.py:MyCompactor --suite practice \
                 --provider anthropic --model claude-haiku-5-5 \
                 --reader-provider anthropic --reader-model claude-haiku-5-5 \
                 --controls --traces traces.jsonl --output results.jsonl
compactbench score --results results.jsonl
compactbench qualify --results results.jsonl
```

`traces.jsonl` shows, per cycle, your artifact, the questions, and the reader's raw
replies — the fastest way to see what your method loses. Use `--estimate` first to see
the token cost.

## Migrating from 0.2

0.2 compactors implemented `compact(self, transcript, config=None, previous_artifact=None)`
and received the **whole** transcript every cycle. In 0.3:

- the signature is `compact(self, request: CompactionRequest)`;
- after cycle 0 you receive only the new turns plus your previous artifact;
- `config` moved to `self.config`;
- there is a token budget (`request.token_budget`).

A class with the old signature fails to load with a message pointing here. The usual port
is: build your prompt from `render_request(request)` instead of the transcript, and stay
under `request.token_budget`.
