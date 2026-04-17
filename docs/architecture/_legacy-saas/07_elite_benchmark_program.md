# 07. Elite Benchmark Program

## 1. Goal

The Elite program is the flagship benchmark program for CompactionBench.

Its objective is not to be "a hard test."  
Its objective is to be:

> the hardest **publicly operated, defensible, anti-overfitting** benchmark program for AI conversation compaction methods that we can build and continuously maintain.

That is the correct target. A one-time static benchmark cannot honestly sustain a "hardest in the market" claim.

## 2. Critical product position

Do not define Elite as a single fixed test pack.

Define it as a **program** with:
- public practice surfaces
- hidden ranked sets
- rotating template families
- seeded deterministic generation
- shadow validation
- version governance

Without that, users will optimize for it.

## 3. Elite program structure

## 3.1 Elite Practice
Purpose:
- transparent practice
- debugging
- education
- user trust

Characteristics:
- public examples
- public template families
- public scoring categories
- no leaderboard qualification

## 3.2 Elite Ranked
Purpose:
- official leaderboard qualification

Characteristics:
- hidden generated cases
- deterministic seed groups
- strict minimum compression thresholds
- mandatory drift cycles
- hidden/public detail split
- versioned ranking space

## 3.3 Elite Shadow
Purpose:
- internal anti-gaming validation

Characteristics:
- never exposed publicly
- used to re-check top methods
- catches benchmark-specialized methods
- can gate publication or flag suspicious runs

## 4. Elite design principles

1. **Generated, not memorized**
2. **Seeded, not noisy**
3. **Versioned, not mutable**
4. **Multi-cycle, not one-shot**
5. **State-fidelity-first, not style-first**
6. **Category-diverse, not single-skill**
7. **Debuggable enough to improve, opaque enough to resist overfitting**

## 5. Elite difficulty characteristics

Elite should stress the exact failure modes that weak compaction methods lose.

Required families:

### 5.1 Buried critical constraints
The only valid answer depends on a rule introduced deep in the middle of noisy context.

### 5.2 Late decision overrides
Earlier decisions are explicitly superseded later. The system must preserve the newest truth.

### 5.3 Negative-rule preservation
"Never do X" and "must not do Y" must survive compaction.

### 5.4 Similar-entity confusion
Multiple entities with overlapping names, dates, ids, or roles.

### 5.5 Exception precedence
A general rule exists, plus one specific exception that takes precedence.

### 5.6 Resolved vs unresolved task continuity
The method must not mark incomplete work as complete or resurrect finished work.

### 5.7 Cross-cycle drift
Correct after one compaction but wrong after repeated compact -> continue loops.

### 5.8 Counterfactual contamination
The conversation mentions alternatives that were explicitly rejected. Those rejected branches must remain dead.

### 5.9 Semantic camouflage
Important state is phrased indirectly or surrounded by distractor language.

### 5.10 Compression pressure
The method must compress aggressively enough to qualify, not merely keep most of the transcript.

## 6. Elite benchmark family catalog

Recommended initial Elite families:

- `buried_constraint_v1`
- `decision_override_v1`
- `negative_rule_v1`
- `entity_confusion_v1`
- `exception_precedence_v1`
- `resolved_vs_unresolved_v1`
- `stale_summary_poison_v1`
- `cross_session_state_v1`
- `drift_decay_v1`
- `conflicting_hypotheses_v1`
- `numeric_near_collision_v1`
- `time_order_inversion_v1`
- `policy_exception_tree_v1`
- `alias_resolution_v1`
- `scope_rejection_persistence_v1`

Each family should be versioned independently.

## 7. Elite generation model

Elite cases are generated from template families using deterministic seed groups.

### Required seeded variables
- entity names
- dates
- prices/quantities
- ordering of selected turns
- paraphrase strategy
- distractor turn placement
- override timing
- exception timing
- unresolved task set
- follow-up continuation prompts

### Rule
Two submissions on the same leaderboard version must be evaluated on the same seed group or an equivalent normalized seed policy. Otherwise scores are not comparable.

## 8. Elite scoring dimensions

Elite leaderboard ranking should not collapse to a single opaque number.

Required tracked dimensions:
- locked decision retention
- forbidden constraint retention
- entity integrity
- exception handling correctness
- unresolved task continuity
- contradiction rate
- stale decision resurrection rate
- drift resistance
- compression ratio

## 9. Minimum qualification rules

A run should not qualify for Elite ranking unless it passes minimum floors.

Recommended floors:
- minimum compression ratio by tier
- contradiction rate below threshold
- all required case slots completed
- all required drift cycles completed
- no callback or scoring failures in ranked slots
- no suspicious replay anomalies

## 10. Compression tiers

Do not allow near-pass-through methods to dominate Elite.

Recommended Elite leaderboard segmentation:
- `Elite-Light`: minimum 2x compression
- `Elite-Mid`: minimum 4x compression
- `Elite-Aggressive`: minimum 8x compression

Do not compare aggressive methods directly against light-compression methods on the same board without normalization.

## 11. Multi-cycle requirement

Elite ranked score must include drift.

Recommended v1:
- cycle 0: initial post-compaction evaluation
- cycle 1: continue, compact again, evaluate
- cycle 2: continue, compact again, evaluate

Recommended future:
- optional 3-5 cycle shadow validations for top methods

## 12. Anti-overfitting controls

### 12.1 Hidden ranked cases
Mandatory.

### 12.2 Public practice / hidden ranked split
Users need to improve without seeing ranked case truth.

### 12.3 Seed rotation by leaderboard version
Do not reuse the same hidden seed group forever.

### 12.4 Shadow evaluations
Run top methods on hidden internal shadow packs before or after publication.

### 12.5 Category diversity requirement
A method cannot top the overall board if it collapses on a critical category.

### 12.6 Suspicion heuristics
Flag methods with:
- unusually low variance across public but high hidden collapse
- abnormal performance concentration on a narrow family
- suspiciously brittle shadow results

## 13. Publication policy

### Publicly visible
- benchmark version
- score categories
- compression tier
- drift score
- rank
- method name
- model

### Not publicly visible
- hidden templates
- hidden seed groups
- exact case content
- exact prompt packs
- full shadow methodology
- internal suspicion heuristics

## 14. Benchmark governance

Elite needs explicit governance, not ad hoc edits.

Recommended governance actions:
- monthly or quarterly Elite version review
- retire compromised template families
- add new template families after observed gaming
- maintain changelog
- keep historical leaderboards pinned to old versions

## 15. Product-copy guidance

Safe claims:
- "ranked on our hardest benchmark program"
- "evaluated on hidden Elite cases"
- "tested under multi-cycle drift"
- "scored on adversarial state-fidelity benchmarks"

Unsafe claims unless continuously validated:
- "hardest test in all of AI"
- "best benchmark in the world"
- "impossible to game"

## 16. Final Elite verdict

If you want Elite to become the benchmark people talk about, it must be:

- versioned
- generated
- hidden where it matters
- seeded and fair
- multi-cycle
- compressive
- continuously hardened

Elite is not a static pack.  
Elite is a competitive benchmark program with governance.
