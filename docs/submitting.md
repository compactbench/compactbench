# Submitting to the leaderboard

!!! note "Ranked submissions are paused"
    Ranked evaluation is paused while the v2 evaluation pipeline is finished. This page
    will describe how to submit when it reopens. Until then, everything below works today.

Ranked scores will come from the **hidden Elite set**, sampled fresh for every ranked run
from private worlds at the same difficulty as the public `practice` suite. There is
nothing fixed to memorize.

## Build and test locally

A method is a Python class that subclasses `compactbench.compactors.Compactor` — see
[Writing a compactor](writing-a-compactor.md). Develop against the public `practice` suite
with any model you like: a hosted one, a local one through Ollama, or your own
OpenAI-compatible server.

```bash
compactbench run --method method.py:MyCompactor --suite practice --cases 4 \
                 --provider openrouter --model qwen/qwen3-235b \
                 --reader-provider anthropic --reader-model claude-haiku-5-5 \
                 --reader-effort high --controls --output results.jsonl
compactbench qualify --results results.jsonl
```

`qualify` applies the same floors the leaderboard does and lists every reason a run would
be rejected. Ranked runs pin every setting — suite, difficulty, compactions, cases, token
budget, and the reader model and its effort — through the season (`seasons/s1.yaml`).

## Rules

- Don't submit a method that has seen hidden content, or that was tuned on hidden results.
- A method must not try to detect or fingerprint ranked cases.
- Your method's source is published with its results — that is the audit trail.
