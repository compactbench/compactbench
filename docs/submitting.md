# Submitting to the leaderboard

Submissions are evaluated against a **hidden** ranked benchmark set by a maintainer-operated runner. This keeps the ranking defensible against overfitting.

## Overview

1. Write and test your compactor against the public `elite_practice` suite.
2. Open a PR adding your method source to `submissions/<your-handle>/<method-name>/`.
3. A maintainer labels the PR for evaluation.
4. The self-hosted runner executes your method against Elite Ranked cases.
5. Scores are posted back to the PR as a comment.
6. If your method qualifies, the PR is merged and the leaderboard updates.

## Submission directory layout

```
submissions/
└─ your-handle/
   └─ method-name/
      ├─ method.py          # subclass of Compactor, exports one public class
      ├─ config.yaml        # method config (provider, model, compression tier, any method-specific knobs)
      ├─ requirements.txt   # third-party pip dependencies beyond compactbench[providers]
      └─ README.md          # one page on your approach
```

A starter scaffold lives at `submissions/_template/`.

## Qualification requirements

Your submission must pass all of these to land on the leaderboard:

- Implements `Compactor` correctly; returns a valid `CompactionArtifact` on every call.
- Declares a compression tier (`Elite-Light` / `Elite-Mid` / `Elite-Aggressive`) and clears the floor (≥ 2× / 4× / 8×).
- Completes all configured cases and all configured drift cycles without errors.
- Contradiction rate ≤ 0.10.
- No single Elite family drops below 0.40 case-level pass rate (category diversity guard).
- Dependencies are pinned in `requirements.txt` and install from PyPI.

Full ranking formula and qualification details: [methodology](methodology.md).

## What gets published

On merge, the leaderboard publishes:

- Your chosen method name
- Your GitHub handle or declared org name
- Overall, drift, constraint retention, contradiction, compression, and per-family scores
- Benchmark version, scorer version, target model, method version

The hidden test content itself is never published.

## Resubmitting

Push new commits to the same PR. Re-evaluation is gated on a maintainer adding the `reevaluate` label so we control runner spend.

New versions of an already-ranked method should go under a new subfolder (`method-name-v2`) so the old entry stays pinned to its benchmark version.
