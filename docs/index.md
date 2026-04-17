# CompactBench

> Open benchmark for AI conversation compaction methods.

Every long-context AI app eventually needs to compact conversation history — drop it into a summary, a structured state object, or some hybrid — and then keep answering correctly with only that compacted representation in hand. CompactBench measures how well different compaction methods actually do that.

We generate adversarial conversations deterministically from versioned templates, compact them with the method under test, replace the original context with the compacted artifact, then ask the model targeted questions that probe what survived compaction. A **hidden ranked set** keeps methods honest: you can develop against public practice templates, but the leaderboard scores you on held-out ones you never see.

## Why this exists

Most LLM benchmarks test the model. CompactBench tests *what you do with long conversations before they hit the model*. That's the layer where apps silently lose user constraints, locked decisions, and entity identities — and where the cost of getting it wrong is highest, because the model can only work with what you passed it.

The benchmarks people trust in 2026 (SWE-bench, MMLU, HELM, Aider) all share the same DNA: open source, versioned, ranked with a public leaderboard, hardened against overfitting via hidden test sets. CompactBench follows that pattern exactly, but targeting a failure mode none of them measure.

## Core properties

- **Deterministic generation** — same template + seed + version always yields the same case. Ranks are reproducible.
- **Hidden ranked set** — public practice templates for development; held-out ranked templates for leaderboard scoring. Overfitting-resistant by construction.
- **Multi-cycle drift** — every ranked method is evaluated across repeated compact → continue → compact cycles. A method that works on turn 0 but degrades by turn 2 is scored for that.
- **State-fidelity scoring** — locked decisions, forbidden behaviors, immutable facts, entity identity. Not output style.
- **Versioned everything** — benchmark suite, template, scorer, model, and method versions travel with every result.

## Quick links

- [Getting started](getting-started.md) — install, first run, local iteration. **3 minutes with Ollama.**
- [Writing a compactor](writing-a-compactor.md) — the `Compactor` interface and the artifact contract.
- [Submitting to the leaderboard](submitting.md) — how to PR a method for ranked scoring.
- [Leaderboard](leaderboard.md) — current rankings.
- [Methodology](methodology.md) — what we measure and why.
- [Elite program](elite-program.md) — the hardest ranked program we maintain.
- [FAQ](faq.md) — common questions.

## Source

[github.com/compactbench/compactbench](https://github.com/compactbench/compactbench) — Apache 2.0 licensed. PRs and issues welcome.
