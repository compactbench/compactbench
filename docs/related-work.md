# Related work

Where CompactBench sits relative to everything else measuring context compaction, memory, and long-context retention — including the work that overlaps it, and the places where somebody else got there first.

This page exists because a benchmark that only cites itself is not credible. If you are deciding whether to use CompactBench, you should be able to see what else exists and choose the right tool, which is sometimes not this one.

!!! note "Last surveyed 2026-08-24"
    Corrections and additions are welcome — open a PR. If we have mischaracterised your work, that is a bug and we will fix it.

## The problem is no longer novel — the standing scoreboard is

Between April and August 2026 the field converged on exactly the question CompactBench was built around, and published it.

### Governance Decay / ConstraintRot

[arXiv:2606.22528](https://arxiv.org/abs/2606.22528) · June 2026

Introduces **Governance Decay**: in-context constraints an agent reliably obeys while visible are silently dropped by compaction, and the same agent then performs the prohibited action. ConstraintRot is a benchmark of long-horizon agent scenarios with deterministic tool-call grading, across seven model families.

Headline result across 1,323 episodes: violation rises from **0% with the policy in full context to 30% after compaction**, reaching **59%** on some models. When the constraint survives the summary, violation stays at 0%; when it is dropped, violation reaches 38%.

**Relationship to CompactBench.** This is the result CompactBench's `buried_constraint` family was designed to produce, published first and at greater scale. We should stop describing that finding as an open question. What ConstraintRot does not do is maintain a live, versioned, submittable leaderboard — it is a paper artifact.

### Lost in Compaction / COMPINT

[arXiv:2608.11242](https://arxiv.org/abs/2608.11242) · July 2026

Evaluates how well compactors preserve **Session Constraints** — user instructions meant to govern behaviour for a whole session — across multi-turn chat, agentic trajectory, and long-horizon research settings. Systematically varies compactor, prompt, context length, constraint phrasing, and injection location.

Headline result: current compactors retain only **17%** of injected session constraints on average. Their proposed SC-aware extractor reaches **90%+** without modifying the compactor or the model.

**Relationship to CompactBench.** The closest existing work to what CompactBench measures, and it is more thorough on constraint phrasing and injection position than our current templates. Code is released. It has **no leaderboard** — which is precisely the gap CompactBench should occupy rather than re-deriving the finding.

### Slipstream

[arXiv:2605.08580](https://arxiv.org/pdf/2605.08580) · 2026

Trajectory-grounded compaction validation for long-horizon agents — validating compaction against the trajectory that produced it rather than against a reference summary.

**Relationship to CompactBench.** Complementary. Slipstream is a validation technique; CompactBench is a scoreboard. A method built on Slipstream is exactly the kind of thing that should be submittable here.

### Letta Context-Bench

[Blog](https://www.letta.com/blog/context-bench/) · [Leaderboard](https://leaderboard.letta.com/) · live

Benchmarks agentic **context engineering** — chaining file operations, tracing entity relationships, multi-step retrieval, and discovering/loading skills — with a maintained public leaderboard.

**Relationship to CompactBench.** Adjacent rather than overlapping: Context-Bench measures how well a model *manages* its context; CompactBench measures what survives when history is *replaced* by a compacted artifact. It is also the clearest evidence that a maintained leaderboard in this space attracts attention, which is the strategy CompactBench should be following.

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

**Separating model drift from compaction drift.** Because the `oracle` control runs the same cycles with full context, CompactBench can distinguish decay caused by the method from decay caused by the model degrading on a longer input. The oracle measures 0.882 drift resistance on our own suite — so the model-attributable floor is real and substantial. See [methodology](methodology.md#the-models-own-drift-floor).

**A standing, versioned scoreboard.** Papers publish a number once. CompactBench pins `suite_version`, `scorer_version`, and `endpoint_kind`, segments rankings on them, and keeps accepting submissions. That is a different artifact from a paper, and it is the one nobody else in this specific area is maintaining.

## Where CompactBench is currently weaker

Stated plainly, because you will find these out anyway:

- **Case scale.** Our "elite" transcripts run ~531 tokens. The regime this benchmark describes — an agent compacting because it is running out of room — begins around 100k. COMPINT tests realistic context lengths and we do not. This is the most important open problem in the project.
- **Synthetic content.** Transcripts are templated and distractors are drawn from a small fixed lexicon. ConstraintRot and COMPINT use richer scenarios.
- **Lexical grading.** Several checks are substring matches, which reject correct paraphrases. Judge-based scoring is planned.
- **No validity study.** No human-agreement data and no demonstrated correlation with downstream task performance. Nobody in this area has published one either, but that is not a defence.

Progress on all four is tracked in the [handover review](https://github.com/compactbench/compactbench/blob/main/docs/reviews/2026-08-handover-review.md).

## Citing

There is no CompactBench paper yet. Cite the repository and pin the versions your numbers came from — `suite_version` and `scorer_version` are recorded in every `results.jsonl`, and scores are not comparable across scorer major versions.
