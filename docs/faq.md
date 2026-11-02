# FAQ

## How is this different from long-context benchmarks?

Long-context benchmarks measure the *model* with everything in its window. CompactBench
measures what happens when the window is replaced by a compacted artifact — repeatedly,
as the conversation continues. You can have the strongest model available; if your
compactor dropped a rule, kept a superseded decision, or swapped two people, the model
will act on that.

## How is compaction different from summarization?

Summarization is one strategy (`naive-summary` is the simplest baseline). Others are
structured state extraction, hierarchical summarization, append-only ledgers, sliding
windows, and provider-native compaction. The benchmark scores whatever artifact you
return.

## Why a separate reader model?

So the method is the only thing that varies. Your method can use any model it likes; the
reader that answers the questions is fixed per run, and pinned per season for ranked runs.
Hold the reader fixed whenever you compare methods.

## Why no LLM judge?

Judges have biases, drift between versions, and cost money on every item. Every
CompactBench answer is an option letter or an exact value, so scoring is free,
deterministic and re-checkable from the traces. Wrong options are built from the
conversation itself, so a structured format doesn't make the questions easier — a
summary that kept the old decision picks the old decision.

## What do the controls tell me?

`--controls` scores the same questions from the full conversation (oracle) and from
nothing (null). The oracle shows what's achievable with that reader; the null shows what
guessing gets. A method at 0.55 with an oracle of 0.90 and a null of 0.10 kept about 56%
of the achievable range.

## Can I run this against my own model?

Yes. Point the `openai` provider at any OpenAI-compatible server with
`COMPACTBENCH_OPENAI_BASE_URL` (vLLM, llama.cpp, LM Studio, OpenRouter…), use `ollama`
for local models, or subclass `Provider`. Custom endpoints are recorded as such.

## Why is there a hidden set if the generator code is public?

The public families drive Starter and Practice. Ranked Elite cases come from private
generators, vocabulary and filler, and every ranked run gets a fresh sample — so there's
nothing fixed to memorize, and Practice is difficulty-matched so it still predicts your
Elite score.

## Why Python?

Open-source AI evaluation is overwhelmingly Python (`lm-evaluation-harness`, `inspect_ai`,
SWE-bench). It keeps the bar to contributing a method low.

## How do I cite CompactBench?

Cite the repository and pin the versions your numbers came from — `suite_version` and
`scorer_version` are in every results file, and scores are not comparable across scorer
major versions:

```
CompactBench: a benchmark for LLM context compaction.
https://github.com/compactbench/compactbench
```

## How do I get in touch?

- Bugs and feature requests: [open an issue](https://github.com/compactbench/compactbench/issues/new)
- Vulnerability reports: see [SECURITY.md](https://github.com/compactbench/compactbench/blob/main/SECURITY.md)
- Everything else: PRs welcome
