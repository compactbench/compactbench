# Forget less: what Season 1 says about compaction instructions

When an agent compacts its context, it rewrites the conversation as a summary and carries on from
that. Whatever the summary drops or gets wrong is gone. Season 1 measured eight ways of writing
that summary on the same 48 hidden conversations, each compacted five times. This page turns the
results into instructions you can paste into your agent.

The numbers below come from the [Season 1 leaderboard](leaderboard.md): Claude Haiku 5.5 writes
the summary and answers the questions, every summary has a 1,024-token budget, and scores are on
a 0-100 scale ([data](data/leaderboard.json)). Per-family scores rest on fewer questions than the
overall score, so read them as directions rather than exact figures.

## What the results show

### 1. Give the summary fixed sections

The plain "summarize the conversation" baseline (`naive-summary`) scored **45.1**. The same single
call with seven fixed headings (`sectioned-summary`) scored **51.9**, the best in Season 1; the
two intervals don't overlap. The headings help most where a plain summary blurs details:

| Family | Plain summary | Sectioned summary |
|---|---:|---:|
| Names and who they refer to (`entity_confusion`) | 20 | 65 |
| Constraints stated once, early (`buried_constraint`) | 48 | 66 |
| Rules with a scope or exception (`conditional_scope`) | 56 | 66 |

### 2. Replace what changed, and say what it replaced

A summary rewritten from the previous summary drifts. `sectioned-summary` answered 73 after the
first compaction and 39 after the fifth. When a question offered a value the conversation had
since replaced, it picked the old value 17% of the time.

`hierarchical-summary` held between 49 and 51 across all five compactions and picked the old
value 4% of the time. Among other differences, its merge step tells the model: where a newer part
of the conversation changes something, keep the newer version and note what it replaced. After
five compactions it was ahead by 10 points. If your sessions compact many times, this is the
property that matters most.

### 3. Track tasks with their status

Keeping track of tasks (what is done, in progress or pending, and who owns it) was the hardest
family for every summary: **10** for the sectioned summary, **5** for the plain one and **17** for
the hierarchical one. `structured-state`, which keeps tasks as explicit records, scored **36**:
the best on this family, although it was weaker overall (40.0).

### 4. Keep each name with its role

`structured-state`'s entity map scored **81** on names and roles, the best in the season,
against 65 for the sectioned summary.

## Instructions to paste

This combines the four findings: the winning method's sections, the instruction from the method
that didn't drift, and explicit task status and roles.

!!! note "Not yet scored as a combination"
    Each part comes from a measured method, but this exact prompt has not been run through the
    benchmark yet. [Check it on your own setup](#measure-it-on-your-setup), and if you do,
    please share the result in an issue.

```text
Your context is being compacted. Write the summary you will continue from; the original
messages will not be available.

Use these sections and keep each one current:
1. Primary request and intent
2. Decisions and constraints: each rule as it stands now, with its scope and exceptions
3. People and responsibilities: each name with its role and what they own
4. Facts and figures: exact numbers, dates, versions and identifiers, copied verbatim
5. Tasks: each one with its status (done, in progress, pending, blocked) and owner
6. Open questions
7. Current state and next step

When something has changed since the earlier summary, write only the new version and add
"(replaced: <old version>)". Drop what was cancelled or reverted. Keep rules that are still
in force, however long ago they were stated.
```

### Claude Code

Add a `# Compact instructions` section to your project's `CLAUDE.md`, and Claude Code uses it
when it compacts:

```markdown
# Compact instructions

When you compact, use these sections and keep each one current:
1. Primary request and intent
...
```

You can also pass instructions to a single manual compaction: `/compact <instructions>`.

### Codex CLI

Set `compact_prompt` in `~/.codex/config.toml` (or point `experimental_compact_prompt_file` at a
file holding the prompt):

```toml
compact_prompt = """
Your context is being compacted. Write the summary you will continue from; ...
"""
```

### LangChain

`SummarizationMiddleware` takes the prompt as `summary_prompt`. It is a format string: keep the
`{messages}` placeholder, and double any other braces.

```python
from langchain.agents import create_agent
from langchain.agents.middleware import SummarizationMiddleware

FORGET_LESS = """Your context is being compacted. ...

<messages>
Messages to summarize:
{messages}
</messages>"""

agent = create_agent(
    model="anthropic:claude-haiku-5-5",
    tools=[...],
    middleware=[
        SummarizationMiddleware(model="anthropic:claude-haiku-5-5", summary_prompt=FORGET_LESS)
    ],
)
```

### LlamaIndex

`ChatSummaryMemoryBuffer.from_defaults(llm=..., token_limit=..., summarize_prompt=FORGET_LESS)`.
LlamaIndex has deprecated this buffer in favour of its newer `Memory` class, so check the current
LlamaIndex docs for where a summary prompt goes there.

## Measure it on your setup

Your agent, model and conversations differ from Season 1's. To see whether a prompt helps, wrap it
as a compactor and compare it with the built-in baseline on the same Practice cases:

```python
# forget_less.py
from typing import ClassVar

from compactbench.compactors import Compactor, fit_to_budget
from compactbench.contracts import CompactionArtifact, CompactionRequest
from compactbench.providers import CompletionRequest
from compactbench.rendering import render_request

PROMPT = """..."""  # the instructions above


class ForgetLess(Compactor):
    name: ClassVar[str] = "forget-less"
    version: ClassVar[str] = "0.1.0"

    async def compact(self, request: CompactionRequest) -> CompactionArtifact:
        limit = f"Stay under {request.token_budget} tokens." if request.token_budget else ""
        response = await self.provider.complete(
            CompletionRequest(
                model=self.model,
                prompt=f"{PROMPT}\n{limit}\n\n{render_request(request)}\n\nSUMMARY:",
                max_tokens=8_000,  # room for thinking on reasoning models
                reasoning_effort="low",
            )
        )
        artifact = CompactionArtifact(summaryText=response.text.strip())
        fitted, _ = fit_to_budget(artifact, request.token_budget)
        return fitted
```

```bash
compactbench check --method built-in:sectioned-summary --cases 12 \
                   --baseline baseline.json --update-baseline
compactbench check --method forget_less.py:ForgetLess --cases 12 --baseline baseline.json
```

The second command reports the change against the sectioned summary, overall and per family.
If your agent uses Codex CLI's or LangChain's default compaction, compare against
`built-in:codex-cli` or `built-in:langchain-summarization` instead: they reproduce those
defaults from the agents' open-source code. See
[checking in CI](ci.md) for the options and [writing a compactor](writing-a-compactor.md) for
the rest of the interface.
