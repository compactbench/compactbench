---
name: measure-compaction
description: Measures how much a context-compaction, conversation-summarization or agent-memory method forgets, using the open CompactBench benchmark on the user's own API keys - wraps the method, estimates the cost, runs a fixed public sample, compares it with a baseline, and can add a CI check that fails on a regression. Use when the user wants to test, benchmark, compare or regression-test a compaction method, a summarization prompt, an agent's compact instructions, or LangChain/LlamaIndex/Codex-style summarization.
when_to_use: Also when the user asks "does my compaction lose things?", "which compaction prompt is better?", or mentions CompactBench.
---

# Measure what a compaction method forgets

CompactBench feeds a method long conversations in which rules are stated once, decisions are
overridden, owners change and figures get corrected, compacts them five times, and has a fixed
reader answer questions from the compacted text only. The score (0-100) is the share answered
right, averaged so each failure family counts equally. Repository:
<https://github.com/compactbench/compactbench>.

Every model call runs on the user's own keys. Never ask the user to paste a key into the chat:
they set it in their environment or in a `.env` file (`COMPACTBENCH_ANTHROPIC_API_KEY`,
`COMPACTBENCH_OPENAI_API_KEY`, `COMPACTBENCH_GROQ_API_KEY`,
`COMPACTBENCH_GOOGLE_AI_STUDIO_API_KEY`, ...).

## Steps

1. **Install.** `compactbench --version` must be 0.3 or later (PyPI's 0.1 is a different,
   older benchmark). Until 0.3 is on PyPI:

   ```bash
   pip install "compactbench[providers] @ git+https://github.com/compactbench/compactbench"
   ```

2. **Wrap the method** as a compactor: copy [references/compactor_template.py](references/compactor_template.py)
   into the user's project and fill in either the prompt (option A) or a call to their own
   code (option B). The interface in one paragraph: `compact(request)` gets the whole
   conversation on the first compaction, and afterwards only the turns since the last one plus
   `request.previous_artifact`, the method's own previous output; it returns
   `CompactionArtifact(summaryText=...)` that must fit `request.token_budget` tokens.
   Frameworks: `compactbench.integrations.langchain.LangChainCompactor` and
   `compactbench.integrations.llamaindex` wrap a callable that takes the framework's messages.

   To measure an agent's default instead of custom code, use a built-in: `built-in:codex-cli`
   (Codex CLI's compaction), `built-in:langchain-summarization` (LangChain's
   SummarizationMiddleware defaults), `built-in:sectioned-summary` (Season 1's best).

3. **Estimate before spending anything**, and tell the user the figure:

   ```bash
   compactbench check --method my_compactor.py:MyCompaction --estimate
   ```

   The default check (4 Practice cases, Claude Haiku 5.5 for the method and the reader) made
   80 calls and cost about $0.11; the estimate leaves out reasoning tokens. Get the user's OK
   before the first real run, since it bills their key. `--provider`/`--model` choose the
   method's model, `--reader-provider`/`--reader-model` the reader (keep the reader fixed when
   comparing).

4. **Compare against a baseline on the same cases.** Record the reference once, then check the
   candidate against it:

   ```bash
   compactbench check --method built-in:sectioned-summary --baseline baseline.json --update-baseline
   compactbench check --method my_compactor.py:MyCompaction --baseline baseline.json
   ```

   The seed group fixes the cases, so the difference comes from the method and the models'
   sampling. For a tighter comparison use `--cases 12` (about three times the cost) for both.

5. **Read the report** for the user: the overall score and its change, the score after each
   compaction (falling numbers mean the method drifts as it re-summarizes its own summary), and
   the family table as a pointer to what it loses. Two identical runs differed by about 1
   point overall while single families moved by up to 23, so don't draw conclusions from one
   family or from a change of a couple of points.

6. **Optionally gate CI** with the GitHub Action: copy
   [references/compactbench-check.yml](references/compactbench-check.yml) to
   `.github/workflows/`, commit the baseline file, and have the user add their key as a
   repository secret. The job fails when the score drops more than `max-drop` points (default
   5). Workflows triggered from forks don't receive secrets.

## Don't

- Don't run a real (non-`--estimate`) check without the user's OK on the cost.
- Don't present a Practice score as a leaderboard result: ranked scores come from the hidden
  Elite set.
- Don't compare runs made with different readers, budgets, case counts or seed groups;
  `compactbench check` refuses such a baseline for that reason.
