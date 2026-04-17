# CompactBench

> Open benchmark for AI conversation compaction methods.

CompactBench measures whether language models still behave correctly after long conversation history is replaced with a compacted representation. It runs adversarial, deterministic, multi-cycle benchmarks and publishes ranked results on a public leaderboard.

## Core properties

- **Deterministic generation** — same template + seed + version always yields the same case.
- **Hidden ranked set** — public practice templates for development; held-out templates for ranked leaderboard scoring.
- **Multi-cycle drift** — every ranked method is evaluated across repeated compact → continue → compact cycles.
- **State-fidelity scoring** — we measure preservation of locked decisions, forbidden behaviors, immutable facts, and entity identity — not output style.
- **Versioned everything** — benchmark suite, template, scorer, model, and method versions travel with every result.

## Quick links

- [Getting started](getting-started.md) — install, first run, local iteration.
- [Writing a compactor](writing-a-compactor.md) — the `Compactor` interface and the artifact contract.
- [Submitting to the leaderboard](submitting.md) — how to PR a method for ranked scoring on the hidden set.
- [Methodology](methodology.md) — what we measure and why.
- [Elite program](elite-program.md) — the hardest ranked program we maintain.

## Source

[github.com/UsernameLoad/compactbench](https://github.com/UsernameLoad/compactbench) — Apache 2.0.
