# Elite benchmark versioning and governance

This document tracks every version of the Elite program — what families ship, which seeds are ranked, and the rules we follow when retiring or adding content. It is the canonical log; if you need to know "what was the v1 Elite set made of," this is where to look.

See [elite-program.md](../elite-program.md) for the design rationale (why Elite is split into Practice + Ranked + Shadow, why hidden content exists, etc.). This page is operational rather than conceptual.

## Active version

**Elite v1** — the launch set.

### v1 families

| Family | Stress mode | Public practice | Hidden ranked |
|---|---|---|---|
| `buried_constraint` | a critical "never X" rule survives under distractors + indirect phrasing | 5 variations | 20 variations |
| `decision_override` | later decision supersedes an earlier one; intermediate options must stay forbidden | 5 variations | 20 variations |
| `entity_confusion` | multiple entities with overlapping names or roles; ownership mapping must not scramble | 5 variations | 20 variations |

Totals: **15 public** (in `benchmarks/public/elite_practice/`), **60 hidden** (in the private `compactbench/compactbench-hidden` repo).

### v1 seed policy

The ranked leaderboard pins a fixed seed group per version. Submissions are evaluated against the **same seeds** so scores are directly comparable.

- Seed group name: `elite_v1_q1`
- Seeds derived from `(suite_version, seed_group, case_slot)` via SHA-256 (see [decisions.md §B1](../architecture/decisions.md))
- Rotation: planned on each minor version bump (see below)

## Version policy

We follow loose SemVer on the Elite program itself.

| Change | Version bump |
|---|---|
| Adding a new family | minor — `v1` → `v2` |
| Retiring a compromised family | patch — `v1.0` → `v1.1` |
| Tightening qualification floors | minor |
| Fixing a template bug that didn't change case semantics | patch |
| Regenerating hidden seed group (anti-overfitting rotation) | minor, with a new `seed_group` name |

When the Elite version bumps, we create a new leaderboard version segmented by `(benchmark_version, target_model)` and leave the old one pinned forever. Historical leaderboards never disappear; they accumulate.

## Retirement

A template or family is retired when one of the following happens:

- **Gaming detected.** A method clearly overfits on a specific template's quirks in a way that doesn't generalize; the template no longer measures what it's supposed to.
- **Leak.** Hidden content appears in a public forum (ours or otherwise) — the variation is burned and must be replaced.
- **Ambiguity.** A template produces cases the ground truth can't reliably score — e.g., multiple equally-valid answers.

Retirement steps:

1. Remove the template from the ranked pool (delete from `compactbench-hidden`).
2. Append a note to this file's changelog explaining what and why.
3. Keep a copy in the private `_retired/` path of the hidden repo for audit.
4. Leave the public practice variation in place if the failure mode is still interesting for development (update the README warning if the template is no longer ranked).

We do **not** silently delete; retirement is always visible in this document.

## Adding a new family

To add a new family (e.g. `stale_summary_poison_v1` from the planned catalog):

1. Open a template proposal issue ([template proposal template](https://github.com/compactbench/compactbench/issues/new?template=template_proposal.md)).
2. Land the public practice variations via PR on the main repo.
3. Add hidden ranked variations via PR on `compactbench-hidden`.
4. Bump the Elite minor version.
5. Update this document: add the family to the active-version table, note any seed-policy changes in the changelog.
6. Create a new leaderboard version; pin the old one.

## Shadow evaluation

For v1, shadow evaluation is **manual** — maintainers periodically re-run top leaderboard entries against a separate shadow seed group and compare. Automated shadow scheduling is deferred (see [decisions.md Part G](../architecture/decisions.md)).

A method that passes ranked but collapses in shadow is flagged for manual review. The suspicion heuristics documented in [elite-program.md §12.6](../elite-program.md) are applied by hand until we automate them.

## Anti-gaming reminders

- **Hidden ranked cases never go into public PRs.** If you're unsure whether something is hidden, ask first.
- **Seed groups rotate on version bumps.** Do not hard-code seed values into methods.
- **The `_retired/` path is audit-only.** Retired templates are not ranked or generated.
- **Category-diversity guard is enforced.** A method that collapses on one family is disqualified regardless of aggregate score (see `qualification.py`).

## Changelog

### v1.0 — 2026-04-17 (active)

- Initial release.
- Families: `buried_constraint`, `decision_override`, `entity_confusion`.
- Public practice: 15 variations across the 3 families.
- Hidden ranked: 60 variations across the 3 families (maintained separately).
- Seed group: `elite_v1_q1`.
