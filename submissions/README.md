# Submissions

Published ranked submissions. Ranked evaluation is paused while the v2 evaluation
pipeline is finished; when it reopens, each qualifying run is written here and the
leaderboard updates.

```
submissions/<github-handle>/<method-name>/
├─ method.py          your method, exactly as submitted (the public audit trail)
├─ requirements.txt   its pinned extra dependencies, if any
├─ submission.json    method, version, provider, model, display name — no keys
├─ results.jsonl      scores only; no conversation text or questions
└─ commitment.json    SHA-256 commitments to the private traces
```

`_template/` is a starting point for writing a method; see
[Writing a compactor](../docs/writing-a-compactor.md). Test it locally against the
public `practice` suite with any model.

Hidden case content is never published. Resubmitting a method replaces its files
here; git history keeps every earlier version.
