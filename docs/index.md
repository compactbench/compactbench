# CompactBench

> The benchmark for LLM context compaction.

Long-running AI agents compact their history before they run out of room — a summary, a
structured state object, a ledger — and carry on with only that. CompactBench measures how
much of what matters survives: across repeated compactions, against conversations built to
make compaction fail.

Each case is a long, generated conversation split into cycles. Your method compacts the
opening conversation, then — cycle after cycle — only its previous artifact plus the new
turns, while rules change, decisions get overridden and ownership moves. After every
compaction a fixed reader model answers structured questions using nothing but the
artifact, and every answer is checked mechanically.

## Why it's built this way

- **The compaction layer, not the model.** The reader only ever sees your artifact.
- **Real drift.** Old turns are never sent again, so anything dropped is gone for good.
- **Adversarial answers.** Wrong options come from the conversation itself — the superseded
  decision, the other project's rule, the look-alike colleague.
- **No judge.** Option letters and exact values, scored for free and re-checkable from traces.
- **Readable scores.** `--controls` scores the same questions from the full conversation and
  from nothing, so every run carries its own ceiling and floor.
- **Hidden ranked set.** Public Starter and Practice suites; ranked Elite cases are generated
  fresh for every run from private generators.
- **Versioned everything.** Suite, scorer, reader, method and budget travel with every result.

## Quick links

- [Getting started](getting-started.md) — install and first run.
- [Writing a compactor](writing-a-compactor.md) — the interface and the artifact.
- [Methodology](methodology.md) — exactly what is measured.
- [Leaderboard](leaderboard.md) — current rankings.
- [Submitting](submitting.md) — how ranked evaluation works.
- [Elite program](elite-program.md) — the ranked track.
- [Related work](related-work.md) — what else exists.
- [FAQ](faq.md)

## Source

[github.com/compactbench/compactbench](https://github.com/compactbench/compactbench) — Apache 2.0. PRs and issues welcome.
