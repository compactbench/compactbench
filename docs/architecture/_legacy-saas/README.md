# [ARCHIVED] CompactionBench — SaaS Architecture Package

> **This document set is archived.** It describes an earlier SaaS-platform shape of the project. On 2026-04-16 the project pivoted to an open-source Python package, and none of the content below reflects the current design.
>
> Current design:
> - [`docs/architecture/decisions.md`](../decisions.md) — locked technical decisions
> - [`docs/architecture/workorders.md`](../workorders.md) — implementation plan
> - [`docs/`](../../) — user-facing methodology and Elite program
>
> Content that survived the pivot (benchmark DSL, artifact schema, scoring formulas, ranking formula, Elite governance) has been migrated forward. Everything SaaS-specific (multi-tenant API, web app, database, billing, hosted infrastructure) was dropped.

---

This package contains the zero-to-launch architecture set for **CompactionBench**, a managed platform for testing and ranking AI conversation compaction methods.

## Goal

Build a SaaS platform where users can:

- register and create projects
- choose benchmark suites and difficulty presets
- test built-in compaction methods
- connect external callback endpoints for custom methods
- run managed evaluations against hosted models
- inspect results, drift behavior, and failure analysis
- optionally publish results to a public leaderboard

## Critical product goal

The **Elite** benchmark program should target the hardest **publicly operated** context-compaction benchmark in the market.

That wording matters. Do **not** hardcode product copy that claims "hardest in the entire AI market" as a fact unless you continuously validate that claim externally. The defensible target is:

- hardest public benchmark we know how to build and operate
- hardest ranked compaction benchmark we can defend with methodology
- continuously hardened through versioned templates, hidden sets, and shadow evaluations

## Files

1. `01_architecture_overview.md`
   - product architecture
   - benchmark model
   - runtime flow
   - deployment topology
   - security and anti-gaming model

2. `02_repo_structure.md`
   - recommended monorepo layout
   - package boundaries
   - local development topology
   - CI/CD notes

3. `03_database_schema.md`
   - canonical database schema list
   - core tables
   - recommended indexes
   - versioning and retention notes

4. `04_api_endpoints.md`
   - v1 API surface
   - public, authenticated, internal, and admin endpoints
   - request/response expectations

5. `05_page_map.md`
   - page map
   - route inventory
   - user flows
   - public vs authenticated surfaces

6. `06_service_responsibilities.md`
   - responsibility split by service/module
   - ownership boundaries
   - failure domains

7. `07_elite_benchmark_program.md`
   - Elite benchmark design
   - hidden/public split
   - seeded randomness
   - anti-overfitting strategy
   - leaderboard qualification policy

8. `08_workorders_bootstrap_to_launch.md`
   - phased workorders from bootstrap to launch
   - acceptance criteria
   - sequencing and dependencies

9. `decisions.md`
   - locked technical decisions for v1 (platform stack, schemas, formulas, policy numbers)
   - authoritative override for any placeholder choices in docs 01–08
   - zero-budget defaults (free tiers, self-hosted, no third-party spend)

## Recommended build order

1. benchmark engine and scoring engine
2. built-in methods
3. private experiment execution
4. external callback methods
5. results explorer
6. public leaderboard
7. Elite program hardening
8. launch readiness

## Non-negotiables

- benchmark engine is the product
- built-in methods are required baselines
- external callback is the v1 custom-method interface
- hidden ranked benchmark sets are mandatory
- deterministic seeded generation is mandatory
- leaderboard entries must be platform-run only
- results must be versioned by benchmark, scorer, model, and method
