# Show HN: CompactBench — a hidden-set benchmark for LLM conversation compaction

## Title (≤80 chars)

Show HN: CompactBench – open hidden-set benchmark for LLM context compaction

## Body

Every long-context LLM app eventually compacts conversation history — summarizes it, extracts structured state, runs some ledger — and then keeps answering with just the compacted representation in hand. Nothing measures how well that compaction actually works.

CompactBench does. We generate adversarial conversations deterministically from versioned templates, compact them with the method under test, replace the original context with the compacted artifact, then ask the model probing questions to see what survived.

Three failure modes in v1:

- **buried_constraint** — a critical "never do X" rule stated deep in noisy context. Did the compactor keep it?
- **decision_override** — a later decision supersedes an earlier one. Does the compacted state reflect the final decision, or does it average?
- **entity_confusion** — multiple entities with overlapping names. Does ownership get scrambled?

Scoring rewards state fidelity, not output style. Compactors are evaluated across multi-cycle drift (compact → continue → compact loops), so a method that works on turn 0 but degrades by turn 2 is scored for that.

Public practice templates (15 of them, all in the repo) let you develop against them. The ranked leaderboard runs on a **hidden** set you never see — maintained in a private sibling repo, rotated on version bumps. The same pattern MMLU and SWE-bench use: you can overfit all you want on practice; the hidden ranked set keeps everyone honest.

Works with Groq, Google AI Studio, Ollama out of the box. Written in Python. Submit a method via PR. Apache 2.0.

Repo: https://github.com/compactbench/compactbench
Docs: https://compactbench.github.io/compactbench/
Leaderboard: https://compactbench.github.io/compactbench/leaderboard/

Would love feedback on the ranking formula, the template families, and anything we missed. Planning to expand the family catalog post-launch based on what people hit in practice.
