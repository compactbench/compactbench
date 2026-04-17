# FAQ

## How is this different from existing benchmarks like MMLU or SWE-bench?

MMLU and SWE-bench measure the *model*: can GPT-4 or Claude 3.5 answer a multi-step question, write a patch? Those benchmarks hand the model everything it needs upfront.

CompactBench measures *what happens between the user and the model* — specifically, what happens when you replace the full conversation with a compacted representation. You can have the smartest model in the world; if your compactor drops a "never do X" constraint, the model will happily do X.

Put another way: MMLU tests raw capability, CompactBench tests the production plumbing that real apps actually run in.

## How is compaction different from summarization?

Summarization is one *strategy* for compaction, and it's the weakest baseline we ship (`naive-summary`). Compaction in the broader sense includes:

- Summarization (prose)
- Structured state extraction (JSON ledgers)
- Hierarchical summarization (chunks → meta-summary)
- Ledger-style accumulation (append-only state across turns)
- Hybrid combinations of the above

The benchmark is deliberately agnostic to strategy — it scores whatever artifact you return, as long as it fits the [compaction artifact schema](methodology.md).

## Can I run this against my own custom model?

Yes. Implement a `Provider` subclass or point an existing provider at your endpoint. The `OllamaProvider` is the reference for local models; the `GroqProvider` and `GoogleAIStudioProvider` show remote API patterns. See [writing-a-compactor](writing-a-compactor.md) and the providers module on GitHub.

## Which model does the leaderboard rank against?

Each leaderboard version pins a specific `(benchmark_version, target_model)` pair. The initial leaderboard uses **Groq + Llama 3.3 70B**. Running against a different model produces a separate leaderboard version; we don't compare cross-model scores directly.

## Why hidden + public split?

Because without it, any serious method quickly overfits. The public practice set is there for you to develop against — you can iterate as long as you want, look at every template, read every variation. The ranked leaderboard runs on a hidden set you never see, curated and rotated by the maintainer team.

If you've only ever trained or prompted against the public set, the ranked set is your first honest test.

## Are all the templates the same family?

No — v1 ships three families:

- **buried_constraint** — a critical "never do X" rule that must survive under distractors
- **decision_override** — a later decision supersedes an earlier one
- **entity_confusion** — multiple entities with overlapping names or roles

More families are on the roadmap (see `docs/elite-program.md`). Contributors can propose new families via GitHub issues.

## How do I know my method hasn't been trained on the ranked templates?

You don't, and neither do we. But:

- The ranked templates are generated deterministically from templates — so even though the template might leak, the *specific cases* at a given seed are reproducible and auditable
- Seed groups rotate on minor Elite version bumps
- Shadow evaluation (manual for now, automated later) re-runs top methods on a separate seed pool

If you believe a method is memorizing rather than generalizing, the right move is to report it via a [template proposal](https://github.com/compactbench/compactbench/issues/new?template=template_proposal.md) for a new family — content diversification is the defense.

## Why Python?

Open-source AI benchmarks are ~95% Python (`lm-evaluation-harness`, `inspect_ai`, `swe-bench`, `GAIA`). Submitting a method in a language the community is already using lowers the bar to contribution. If we got traction in another language, a runtime bridge could come later.

## What happens to methods that game the leaderboard?

Retirement. If a method clearly overfits on a specific template's quirks and the template no longer measures what it's supposed to, the template moves to `_retired/` in the hidden repo (preserved for audit) and a replacement ships with the next Elite version. Governance policy is in [docs/governance/elite-versions.md](governance/elite-versions.md).

## How do I cite CompactBench?

We don't have a paper yet. For now, cite the repo:

```
CompactBench: Open benchmark for AI conversation compaction methods.
https://github.com/compactbench/compactbench
```

## How do I get in touch?

- Bugs / feature requests: [open an issue](https://github.com/compactbench/compactbench/issues/new)
- Method submission questions: comment on [#5](https://github.com/compactbench/compactbench/issues/5)
- Vulnerability reports: see [SECURITY.md](https://github.com/compactbench/compactbench/blob/main/SECURITY.md)
- Everything else: PR welcome
