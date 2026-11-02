# Related work

Where CompactBench sits relative to everything else measuring context compaction, memory, and long-context retention — including the work that overlaps it, and the places where somebody else got there first.

This page exists because a benchmark that only cites itself is not credible. If you are deciding whether to use CompactBench, you should be able to see what else exists and choose the right tool, which is sometimes not this one.

!!! note "Last surveyed 2026-11-01"
    Corrections and additions are welcome — open a PR. If we have mischaracterised your work, that is a bug and we will fix it.

## The problem is no longer novel — the standing scoreboard is

Between April and August 2026 the field converged on exactly the question CompactBench was built around, and published it.

### Governance Decay / ConstraintRot

[arXiv:2606.22528](https://arxiv.org/abs/2606.22528) · June 2026

Introduces **Governance Decay**: in-context constraints an agent reliably obeys while visible are silently dropped by compaction, and the same agent then performs the prohibited action. ConstraintRot is a benchmark of long-horizon agent scenarios with deterministic tool-call grading, across seven model families.

Headline result across 1,323 episodes: violation rises from **0% with the policy in full context to 30% after compaction**, reaching **59%** on some models. When the constraint survives the summary, violation stays at 0%; when it is dropped, violation reaches 38%.

**Relationship to CompactBench.** This is the result CompactBench's `buried_constraint` family measures, published first and at greater scale, so it isn't an open question. ConstraintRot is a paper artifact rather than a live, versioned, submittable leaderboard.

### Lost in Compaction / COMPINT

[arXiv:2608.11242](https://arxiv.org/abs/2608.11242) · July 2026

Evaluates how well compactors preserve **Session Constraints** — user instructions meant to govern behaviour for a whole session — across multi-turn chat, agentic trajectory, and long-horizon research settings. Systematically varies compactor, prompt, context length, constraint phrasing, and injection location.

Headline result: current compactors retain only **17%** of injected session constraints on average. Their proposed SC-aware extractor reaches **90%+** without modifying the compactor or the model.

**Relationship to CompactBench.** Close to what CompactBench measures, and thorough on constraint phrasing and injection position. Code is released; there is no leaderboard.

### Compact-Bench (coding agents)

[arXiv:2610.31710](https://arxiv.org/abs/2610.31710) · October 2026 · [code](https://github.com/cai-jianfeng/compact-bench)

Measures what compaction costs long-horizon **coding agents** by pairing full-history and
summary-only continuations from a shared repository state, across SWE-bench repairs,
agentic sessions and production compaction chains. Reports that LLM summaries retain at
most 16% of recurring details, versus 79% for mechanical extraction.

**Relationship to CompactBench.** Similar name, different artifact: a coding-agent study
with a public dataset, where CompactBench is a domain-general, multi-cycle benchmark with a
hidden ranked set and a standing leaderboard. Its mechanical-extraction finding is a useful
baseline for anyone building a method here.

### Slipstream

[arXiv:2605.08580](https://arxiv.org/pdf/2605.08580) · 2026

Trajectory-grounded compaction validation for long-horizon agents — validating compaction against the trajectory that produced it rather than against a reference summary.

**Relationship to CompactBench.** Complementary. Slipstream is a validation technique; CompactBench is a scoreboard. A method built on Slipstream is exactly the kind of thing that should be submittable here.

### Letta Context-Bench

[Blog](https://www.letta.com/blog/context-bench/) · [Leaderboard](https://leaderboard.letta.com/) · live

Benchmarks agentic **context engineering** — chaining file operations, tracing entity relationships, multi-step retrieval, and discovering/loading skills — with a maintained public leaderboard.

**Relationship to CompactBench.** Adjacent rather than overlapping: Context-Bench measures how well a model *manages* its context; CompactBench measures what survives when history is *replaced* by a compacted artifact. It is also evidence that a maintained leaderboard in this space is useful to people.

## Long-context benchmarks that are frequently confused with this

These measure whether a model can *find* information in a long context. CompactBench measures what survives when that context is **deliberately destroyed and replaced**. If your question is "can the model use 200k tokens", these are the right tools and CompactBench is not.

| Benchmark | Measures | Why it is not this |
|---|---|---|
| Needle-in-a-Haystack | Retrieval of a planted fact from long context | Full context is present; nothing is compacted |
| RULER | Synthetic long-context tasks at controlled lengths | Same — context is intact |
| LongBench / ∞Bench | Long-document understanding | Document comprehension, not conversational state |
| BABILong | Reasoning over facts spread through long context | No compaction step |
| HELMET | Long-context evaluation across task types | No compaction step |

## Where CompactBench is genuinely differentiated

Being honest about this is more useful than overclaiming:

**Multi-cycle drift.** Most work compacts once and measures what was lost. CompactBench compacts repeatedly — compact → continue → compact — and treats decay across cycles as a first-class metric. As of the 2026-08 survey we are not aware of another public benchmark that does this, and it is the failure mode production agents actually hit, because they compact many times over a long session.

**Separating model limits from compaction losses.** With `--controls`, every run also scores the same questions from the full conversation (oracle) and from nothing (null), on the same cases. A method's score is read against that bracket rather than against 1.0, which separates what the reader can't do from what the method lost.

**Real multi-cycle state.** After the first compaction a method only ever gets its previous artifact plus new turns, while later cycles change rules, override decisions and move ownership. Wrong answers are built from that history, so a stale artifact is measured as stale, not just incomplete.

**A standing, versioned scoreboard.** Papers publish a number once. CompactBench pins `suite_version`, `scorer_version`, the reader model and the token budget, segments rankings on them, and keeps accepting submissions — ranked against a hidden set that is sampled fresh for every run.

## Where CompactBench is currently weaker

Stated plainly, because you will find these out anyway:

- **Synthetic content.** Conversations are procedurally generated from templates and vocabularies, not taken from real agent sessions. The filler is on-topic and adversarial, but it is not real.
- **One setting.** Every case is a software-project conversation. Support, research and operations sessions fail differently.
- **Scale.** The hardest public suite opens at ~32k tokens and grows by ~8k per cycle. Production agents often compact at 100k+.
- **No validity study yet.** No human-agreement data and no demonstrated correlation with downstream task success. Nobody in this area has published one either, but that is not a defence.

## Citing

There is no CompactBench paper yet. Cite the repository and pin the versions your numbers came from — `suite_version` and `scorer_version` are recorded in every `results.jsonl`, and scores are not comparable across scorer major versions.
