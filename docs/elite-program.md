# Elite program

The Elite program is CompactBench's hardest benchmark track. It is not a single fixed test pack — it is a versioned program maintained with explicit governance.

## Goal

> The hardest **publicly operated, defensible, anti-overfitting** benchmark program for AI conversation compaction methods we can build and continuously maintain.

A one-time static benchmark cannot honestly sustain a "hardest" claim. Elite is maintained as a program so the claim can hold.

## Structure

| Track | Visibility | Purpose |
|---|---|---|
| **Elite Practice** | public templates, public seeds | transparent practice, debugging, education |
| **Elite Ranked** | hidden templates, rotating seeds | official leaderboard qualification |
| **Elite Shadow** | never exposed | internal anti-gaming validation of top methods |

Users develop against Practice, submit against Ranked, and top methods are periodically re-checked on Shadow.

## Failure modes targeted

Elite cases stress the compaction failure modes that weak methods lose:

- Buried critical constraints
- Late decision overrides
- Negative-rule preservation ("never do X")
- Similar-entity confusion
- Exception precedence (general rule + specific exception)
- Resolved vs unresolved task continuity
- Cross-cycle drift degradation
- Counterfactual contamination (rejected branches staying dead)
- Semantic camouflage
- Compression pressure (methods that barely compress should not dominate)

## Launch families (v1)

Three families ship with the first release:

| Family | Stress mode |
|---|---|
| `buried_constraint_v1` | constraint survives deep in a noisy transcript |
| `decision_override_v1` | later decision overrides an earlier one |
| `entity_confusion_v1` | multiple entities with overlapping names and roles |

Each family ships with 5 public practice variations and 20 hidden ranked variations. Additional families are added post-launch.

## Compression tiers

Elite segments the leaderboard by compression tier so aggressive methods never compete directly with near-pass-through ones:

- **Elite-Light** — ≥ 2× compression
- **Elite-Mid** — ≥ 4× compression
- **Elite-Aggressive** — ≥ 8× compression

## Multi-cycle requirement

Elite Ranked runs include drift:

- cycle 0: initial evaluation after first compaction
- cycle 1: continue → compact → evaluate
- cycle 2: continue → compact → evaluate

Three-to-five-cycle validations are used in Shadow on top methods.

## Anti-gaming controls

- Hidden ranked cases never leak through public APIs or published artifacts.
- Seed groups rotate on leaderboard version changes.
- Shadow evaluations spot-check the top of the leaderboard.
- Methods must maintain ≥ 0.40 on every family — a specialist that collapses on one family cannot win overall.
- Suspicion heuristics flag unusual patterns (low public variance + hidden collapse, extreme family concentration, brittle shadow results) for maintainer review.

## Governance

- Elite versions are reviewed quarterly.
- Compromised template families are retired.
- New families are added after observed gaming or new failure modes.
- Historical leaderboards stay pinned to their original Elite version.
- A public changelog records every version transition.

## Product-copy guidance

Safe to claim:

- "ranked on the hardest benchmark program we maintain"
- "evaluated on hidden Elite cases"
- "tested under multi-cycle drift"
- "scored on adversarial state-fidelity benchmarks"

Not safe without continuous external validation:

- "hardest test in all of AI"
- "best benchmark in the world"
- "impossible to game"
