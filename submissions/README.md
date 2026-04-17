# Submissions

This folder holds community-submitted compaction methods. Each submission is a PR placed at:

```
submissions/<your-handle>/<method-name>/
```

A maintainer-operated runner evaluates new submissions against hidden Elite Ranked cases and posts scores back to the PR. Qualifying runs land on the public leaderboard at [compactbench.dev](https://compactbench.dev).

## Before you submit

Read [docs/submitting.md](../docs/submitting.md). Short version:

1. Implement a class that subclasses `compactbench.compactors.Compactor`.
2. Test it locally against `compactbench run --suite elite_practice`.
3. Copy `submissions/_template/` as your scaffold and edit in place.
4. Open a PR.

## What gets published on merge

- Method name + your handle (or declared org name)
- Overall, drift, constraint retention, contradiction, compression, per-family scores
- Benchmark version, scorer version, target model, method version

The hidden test content is never published, and your raw method source stays in the public repo under your submission folder — that's the audit trail.

## Honesty norms

- Don't submit a method that has seen any hidden case content.
- Don't fine-tune on the public practice set in a way that's indistinguishable from memorization.
- If you used the leaderboard runner's responses to iterate, disclose it in your PR.

Results that rely on hidden-case exposure are removed and the submitter is banned from the board.
