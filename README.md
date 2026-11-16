# CompactBench

> **Your agent compacts its context before it runs out of room. Does it keep what matters?** CompactBench is the benchmark that finds out.

[![PyPI version](https://img.shields.io/pypi/v/compactbench.svg)](https://pypi.org/project/compactbench/)
[![Python](https://img.shields.io/pypi/pyversions/compactbench.svg)](https://pypi.org/project/compactbench/)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](https://github.com/compactbench/compactbench/blob/main/LICENSE)
[![CI](https://github.com/compactbench/compactbench/actions/workflows/ci.yml/badge.svg)](https://github.com/compactbench/compactbench/actions/workflows/ci.yml)
[![Docs](https://img.shields.io/badge/docs-compactbench.com-black)](https://compactbench.com/docs)
[![Open in Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/compactbench/compactbench/blob/main/notebooks/try_compactbench.ipynb)

Long-running LLM agents compact their history — summarize it, extract state, keep a ledger — and then carry on with only the compacted version. CompactBench gives your compactor a long, adversarial conversation, compacts it again and again as the conversation continues, and after every compaction asks a fixed reader model structured questions about what survived.

**What makes it different:**

- **It measures the compaction layer, not the model.** The reader only ever sees your artifact.
- **Real multi-cycle drift.** After the first compaction your method gets only its previous artifact plus the new turns — never the old turns again — while rules change, decisions get overridden, and ownership moves.
- **Adversarial by construction.** Wrong answers are built from the conversation itself: the superseded decision, the rule for another project, the look-alike colleague, the runner-up vendor.
- **No LLM judge.** Every answer is an option letter or an exact value, scored mechanically, with confidence intervals.
- **Controls.** `--controls` scores the same questions from the full conversation (ceiling) and from nothing (floor); every season publishes both, so a score is always readable.
- **Any model.** Your method can call any hosted model or your own OpenAI-compatible endpoint; one fixed reader grades everyone the same way.
- **Hidden ranked set.** Public Starter and Practice suites for development; ranked scores come from a hidden Elite set generated fresh for each run.

## 30-second try

**In your browser:** open [`notebooks/try_compactbench.ipynb`](notebooks/try_compactbench.ipynb) in Colab ([direct link](https://colab.research.google.com/github/compactbench/compactbench/blob/main/notebooks/try_compactbench.ipynb)) — no local install, runs on Groq's free tier.

**Locally:**

```bash
pip install 'compactbench[providers]'
export COMPACTBENCH_ANTHROPIC_API_KEY=...
compactbench run --method built-in:hybrid-ledger --suite starter \
                 --provider anthropic --model claude-haiku-5-5 --controls
compactbench score --results results.jsonl
```

Built-in methods: `naive-summary`, `sectioned-summary`, `structured-state`, `hierarchical-summary`, `hybrid-ledger`, `extractive` (no model calls), Anthropic's server-side compaction (`anthropic-compaction`), the default compaction of Codex CLI (`codex-cli`) and LangChain's summarization middleware (`langchain-summarization`) reproduced from their open-source code, plus the controls `oracle`, `null` and `truncate-last-n`. Providers: Anthropic, OpenAI (and any OpenAI-compatible server), Groq, Google AI Studio, Ollama.

## Suites

| Suite | What it is | Opening conversation | Drift cycles |
|---|---|---|---|
| `starter` | Smoke test — check your method runs end to end | ~1.5k tokens | 2 |
| `practice` | Public twin of the ranked Elite set: mixed sessions, same difficulty | ~32k tokens | 4 |
| `drills` | One family per case at Elite difficulty, to work on one failure mode | ~32k tokens | 4 |
| Elite (hidden) | The ranked set: mixed sessions in private worlds, a fresh sample per run | ~32k tokens | 4 |

The public suites are also on Hugging Face as [`compactbench/compactbench`](https://huggingface.co/datasets/compactbench/compactbench) (`load_dataset("compactbench/compactbench", "practice")`), built by `scripts/hf_dataset.py`.

A mixed session puts every family into one conversation under one token budget. Eight families, each a different way compaction fails: `buried_constraint`, `decision_override`, `entity_confusion`, `reference_resolution`, `numeric_precision`, `conditional_scope`, `task_continuity` and `provenance_authority`. List them with `compactbench families list`, or read one with `compactbench generate --family decision_override --seed 7 --text`.

## Writing your own compactor

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
        # cycle 0: request.turns is the whole conversation.
        # later:   request.previous_artifact + only the new turns.
        response = await self.provider.complete(
            CompletionRequest(
                model=self.model,
                prompt="Update the summary:\n\n" + render_request(request),
                max_tokens=8_000,  # room for thinking on reasoning models
                reasoning_effort="low",
            )
        )
        return CompactionArtifact(summaryText=response.text.strip())
```

```bash
compactbench run --method path/to/my_compactor.py:MyCompactor --suite practice \
                 --provider anthropic --model claude-haiku-5-5 --controls --traces traces.jsonl
compactbench qualify --results results.jsonl
```

Already running LangChain or LlamaIndex? Wrap it with `compactbench.integrations` (`pip install 'compactbench[langchain]'` or `[llamaindex]`). See [writing a compactor](https://compactbench.com/docs/writing-a-compactor) and [integrations](https://compactbench.com/docs/integrations).

## Forget less

Season 1 shows what makes a compaction summary hold up: fixed sections, replacing changed facts instead of keeping both, and tracking tasks with their status. [Forget less](https://compactbench.com/docs/forget-less) turns that into instructions you can paste into Claude Code, Codex, LangChain or LlamaIndex, and shows how to measure them on your own setup.

## Claude Code plugin

The `compactbench` plugin brings this into Claude Code: a `forget-less` skill that writes evidence-based compact instructions for your `CLAUDE.md` (or your agent's summarization prompt), and a `measure-compaction` skill that benchmarks a compaction method on your own keys and can set up the CI check below.

```
/plugin install compactbench --marketplace compactbench/compactbench
```

(Or `/plugin marketplace add compactbench/compactbench`, then `/plugin install compactbench@compactbench`.)

## Check your method in CI

`compactbench check` runs a small, fixed Practice sample of your method with your keys and fails when the score drops below a saved baseline. The GitHub Action wraps it and posts the report on the pull request:

```yaml
- uses: compactbench/compactbench@main # pin a release tag or commit SHA
  with:
    method: my_compactor.py:MyCompactor
    baseline: .compactbench/baseline.json
    comment: true
  env:
    COMPACTBENCH_ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
```

See [checking in CI](https://compactbench.com/docs/ci).

## Leaderboard

Season 1's reference baselines are on the **[leaderboard](https://compactbench.com/leaderboard)** (data: [`docs/data/leaderboard.json`](https://github.com/compactbench/compactbench/blob/main/docs/data/leaderboard.json)).

**Ranked submissions are open** at [compactbench.com/submit](https://compactbench.com/submit): sign in with GitHub, upload your method (or pick a reference method and benchmark your model), and bring your own API keys; it runs sandboxed on a fresh sample of the hidden Elite set and publishes itself when it qualifies. Develop against the public `practice` suite — it's the same difficulty — and check your run with `compactbench qualify` first. See [submitting](https://compactbench.com/submit).

## Project status

**0.3** is benchmark v2 — a rewrite of case generation, scoring and the compaction loop. It replaces 0.2's templates and scorer, and scores are not comparable across the two. See [CHANGELOG.md](https://github.com/compactbench/compactbench/blob/main/CHANGELOG.md) and the [methodology](https://compactbench.com/methodology).

## Contributing

Bug reports, new scenario families, and new compactors are welcome. See [CONTRIBUTING.md](https://github.com/compactbench/compactbench/blob/main/CONTRIBUTING.md) and our [Code of Conduct](https://github.com/compactbench/compactbench/blob/main/CODE_OF_CONDUCT.md).

## License

Apache License 2.0 — see [LICENSE](https://github.com/compactbench/compactbench/blob/main/LICENSE).
