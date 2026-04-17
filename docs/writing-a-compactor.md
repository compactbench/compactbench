# Writing a compactor

A compactor takes a transcript and returns a `CompactionArtifact`. That's the whole contract.

## The `Compactor` class

```python
from typing import Any

from compactbench.compactors import Compactor
from compactbench.contracts import (
    CompactionArtifact,
    StructuredState,
    Transcript,
)


class MyCompactor(Compactor):
    name = "my-method"
    version = "0.1.0"

    def compact(
        self,
        transcript: Transcript,
        config: dict[str, Any] | None = None,
        previous_artifact: CompactionArtifact | None = None,
    ) -> CompactionArtifact:
        return CompactionArtifact(
            summaryText="A short overview of the conversation.",
            structured_state=StructuredState(
                immutable_facts=["project: X"],
                locked_decisions=["use approach A"],
                forbidden_behaviors=["do not B"],
                unresolved_items=["decide on C"],
                entity_map={"Alice": "primary_stakeholder"},
            ),
            selectedSourceTurnIds=[t.id for t in transcript.turns],
            warnings=[],
            methodMetadata={"temperature": 0.0},
        )
```

## The artifact schema

Every field in `CompactionArtifact` is required — empty arrays and empty objects are fine; missing keys are not.

| Field | Purpose |
|---|---|
| `summaryText` | Free-form summary (≤ 8000 chars). Optional; leave empty for no-prose methods. |
| `structured_state.immutable_facts` | Facts that must never change (entities, versions, file paths). |
| `structured_state.locked_decisions` | Decisions the user has committed to. |
| `structured_state.deferred_items` | Items explicitly postponed. |
| `structured_state.forbidden_behaviors` | Things the assistant must never do. |
| `structured_state.entity_map` | Canonical mapping of entity names to roles. |
| `structured_state.unresolved_items` | Open tasks or questions. |
| `selectedSourceTurnIds` | Turn ids the method drew from. |
| `warnings` | Non-fatal issues the method encountered. |
| `methodMetadata` | Anything method-specific the scorer should ignore. |

The Pydantic validator will reject any extra fields.

## Testing locally

Use the mock provider for reproducible local iteration:

```bash
compactbench run \
  --method path/to/my_compactor.py:MyCompactor \
  --suite starter \
  --provider mock \
  --drift-cycles 2
```

Then inspect `results.jsonl`.

## Handling drift cycles

If you want to accumulate state across cycles (the strongest baseline — `hybrid-ledger` — does this), use the `previous_artifact` argument:

```python
def compact(
    self,
    transcript: Transcript,
    config: dict[str, Any] | None = None,
    previous_artifact: CompactionArtifact | None = None,
) -> CompactionArtifact:
    carried_locked = (
        list(previous_artifact.structured_state.locked_decisions)
        if previous_artifact
        else []
    )
    # ... merge with newly observed decisions ...
```

Stateless methods should simply ignore `previous_artifact`.

## Ready to submit?

See [submitting to the leaderboard](submitting.md).
