# Methodology

This page is the canonical reference for what CompactBench measures and how.

## What a benchmark case contains

Every case has:

- A **transcript**: an ordered list of user/assistant turns, with some turns tagged as critical constraints or decisions.
- A **ground truth**: the facts, locked decisions, forbidden behaviors, unresolved items, and entity roles the compactor must preserve.
- **Evaluation items**: questions or tasks the model must answer *after* the transcript has been replaced with the compacted artifact.

Transcripts and ground truth are generated deterministically from a versioned template and a seed.

## What a run measures

For each case the runner:

1. Invokes your method on the transcript → produces a `CompactionArtifact`.
2. Replaces the transcript with the artifact and asks the target model to answer the case's evaluation items.
3. Repeats steps 1–2 for each drift cycle (default: 2 cycles).
4. Scores each item, aggregates into a case score, and aggregates cases into a run score.

## Item weights

| Item type | Weight |
|---|---|
| `locked_decision_retention` | 3 |
| `forbidden_behavior_retention` | 3 |
| `immutable_fact_recall` | 2 |
| `unresolved_task_continuity` | 2 |
| `entity_integrity` | 1 |
| `planning_soundness` | 1 |

Per-cycle score is the weighted mean of item scores.

## Contradiction penalty

Any response that violates a `locked_decision` or a `forbidden_behavior` contributes to the contradiction rate:

```
contradiction_rate = violating_responses / total_responses
penalized_cycle_score = cycle_score * (1 - contradiction_rate)
```

## Drift resistance

```
drift_delta_n   = cycle_score_n - cycle_score_0
drift_resistance = clamp(1 + mean(drift_delta_n for n >= 1), 0, 1)
```

A method that holds steady scores 1.0. A method that degrades across cycles scores below 1.0 proportionally.

## Compression ratio

```
compression_ratio = tokens(transcript) / (tokens(summary_text) + tokens(structured_state))
```

Tokenizer is `cl100k_base` (tiktoken), applied consistently across all methods and models so ratios are directly comparable.

## Leaderboard ranking

```
elite_score =
    0.40 * run_overall_score
  + 0.30 * drift_resistance
  + 0.20 * constraint_retention
  + 0.10 * compression_bonus
```

Tie-breakers in order: higher drift_resistance → higher constraint_retention → lower contradiction_rate → earlier `published_at`.

## Qualification floors

All of the following must pass for a run to qualify for the leaderboard:

- `compression_ratio ≥ tier_floor` (2× / 4× / 8× by tier)
- `contradiction_rate ≤ 0.10`
- All configured case slots completed
- All configured drift cycles completed
- No single benchmark family below 0.40 pass rate
- No callback, scoring, or runner failures in ranked slots

## Determinism and reproducibility

- Every case is generated from `(template_version, seed_group, case_slot)`. Reproducing the generation only requires those three values.
- Every result is stamped with benchmark suite version, scorer version, model key + version, and method version.
- Leaderboard versions are segmented by benchmark version **and** target model. Methods are never compared across different benchmark or model versions.
