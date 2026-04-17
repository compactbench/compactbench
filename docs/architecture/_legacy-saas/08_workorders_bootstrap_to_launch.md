# 08. Workorders — Bootstrap to Launch

## Workorder format

Each workorder below is written as a strict implementation planning unit.

Each includes:
- objective
- scope
- key deliverables
- dependencies
- acceptance criteria
- failure conditions / notes

## Phase 0 — Foundations and product truth

---

## WO-001 — Monorepo Bootstrap and Local Runtime

### Objective
Create the initial private monorepo with web, API, worker, shared packages, Docker local runtime, and baseline developer tooling.

### Scope
- monorepo skeleton
- app shells for web/api/worker
- package shells for contracts, benchmark engine, scoring engine, built-in compactors, leaderboard core
- Docker Compose for local runtime
- env configuration pattern
- Makefile or task runner
- README bootstrap instructions

### Deliverables
- repo structure from `02_repo_structure.md`
- `docker-compose.yml`
- local `.env.example`
- healthcheck endpoints or equivalent
- basic CI pipeline shell

### Dependencies
None.

### Acceptance criteria
- a developer can clone, configure env, and start all local services with one command
- web, API, worker, Postgres, Redis, and object storage emulator all boot successfully
- repo builds cleanly in CI

### Failure conditions / notes
Fail if hidden benchmark content is bundled anywhere at bootstrap. Keep only public sample fixtures.

---

## WO-002 — Identity, Teams, Projects, and Access Control

### Objective
Implement the core tenancy and access model.

### Scope
- users
- teams
- team members
- invites
- projects
- permission enforcement middleware/policies

### Deliverables
- DB tables for user/team/project domain
- API endpoints for teams, invites, projects
- basic authenticated UI pages
- audit logging for membership/admin actions

### Dependencies
WO-001.

### Acceptance criteria
- users can sign up / sign in using chosen auth model
- users can create a team and project
- non-members cannot access another team’s projects
- invites and role assignment work end-to-end

### Failure conditions / notes
Backend must own authorization. No frontend-only access checks.

---

## WO-003 — Shared Contracts and Schema Validation

### Objective
Create canonical contracts so web, API, worker, and external callback methods share the same shapes.

### Scope
- DTOs
- JSON Schemas
- compaction artifact schema (canonical definition in `decisions.md` §B2)
- benchmark case schema
- result schema
- version constants (schemaVersion = 1.0.0)

### Deliverables
- `packages/contracts`
- schema validation library integration
- contract test coverage

### Dependencies
WO-001.

### Acceptance criteria
- API and worker both validate compaction artifacts against same schema
- invalid payloads fail fast with explicit errors
- version identifiers are included in core DTOs

### Failure conditions / notes
Do not let built-in methods bypass schema validation. They must go through the same artifact contract.

---

## WO-004 — Core Database Schema and Migrations

### Objective
Create the initial Postgres schema for all first-class domains.

### Scope
- tables from `03_database_schema.md` up through run execution, scoring, artifacts, and leaderboard foundations
- migration tooling
- seed data for local development

### Deliverables
- migration history
- DB initialization scripts
- local seed command

### Dependencies
WO-001, WO-003.

### Acceptance criteria
- schema can be built from zero through migrations
- local dev seed creates usable sample users/projects/suites/methods
- indexes exist for hot query paths

### Failure conditions / notes
Do not defer indexes and retention thinking. Query cost will rise quickly once runs accumulate.

---

## WO-005 — API Control Plane Shell

### Objective
Stand up the API control plane structure and foundational middleware.

### Scope
- routing
- auth integration (ASP.NET Core Identity + Google/GitHub OAuth, per `decisions.md` §A1)
- validation pipeline
- error handling
- logging/tracing (Serilog → OpenTelemetry, per `decisions.md` §A10)
- rate-limiting foundation (Redis-backed, limits from `decisions.md` §B7)
- health and readiness

### Deliverables
- API middleware stack
- consistent error envelope
- `/v1/me`
- placeholder endpoints for projects, methods, suites, and runs

### Dependencies
WO-001, WO-002, WO-003, WO-004.

### Acceptance criteria
- authenticated and unauthenticated routes behave correctly
- errors are typed and logged
- API is ready for domain modules to attach

### Failure conditions / notes
No benchmark generation or scoring logic in controllers.

---

## Phase 1 — Benchmark engine and scoring core

---

## WO-006 — Benchmark Catalog Domain

### Objective
Implement benchmark suite and version cataloging.

### Scope
- suites
- suite versions
- public vs hidden visibility
- difficulty tagging
- eligibility metadata

### Deliverables
- suite tables and APIs
- admin catalog management skeleton
- public suite catalog API
- authenticated suite detail API

### Dependencies
WO-004, WO-005.

### Acceptance criteria
- public suites can be browsed
- hidden suites are not exposed to standard users
- suite versions are immutable once published

### Failure conditions / notes
Do not mutate published suite versions in place.

---

## WO-007 — Benchmark Template DSL and Parser

### Objective
Create the internal DSL for template-driven benchmark generation. Canonical YAML structure in `decisions.md` §B1.

### Scope
- template schema (YAML + JSON Schema validator)
- parser/compiler
- Handlebars-style `{{variable}}` substitution
- validation rules
- family abstraction
- variable schema definition
- difficulty policy structure
- seeded generators: `person_name`, `action_phrase`, `project_noun`, `date_iso`, `amount_usd`, `product_sku`, `org_name`

### Deliverables
- `packages/benchmark-dsl`
- parser and validation tests
- sample public templates
- admin-only hidden template import path

### Dependencies
WO-003, WO-006.

### Acceptance criteria
- invalid templates fail validation
- template family/version structure is explicit
- deterministic seed inputs produce deterministic compiled forms

### Failure conditions / notes
This is one of the core product assets. Do not bury DSL rules inside random service code.

---

## WO-008 — Deterministic Case Generation Engine

### Objective
Generate concrete test cases from template versions and seeds.

### Scope
- transcript generation
- ground-truth generation
- evaluation item generation
- paraphrase/noise hooks
- difficulty scaling

### Deliverables
- `packages/benchmark-engine`
- case generation API for worker use
- deterministic regression tests

### Dependencies
WO-007.

### Acceptance criteria
- same template + seed + version always yields same case
- generated case includes transcript, ground truth, and evaluation items
- difficulty policies affect output in predictable ways

### Failure conditions / notes
If generation is not deterministic, the leaderboard is not trustworthy.

---

## WO-009 — Seed Sets, Hidden/Public Suite Controls, and Benchmark Governance

### Objective
Implement seed-set management and hidden/public suite administration.

### Scope
- seed_set persistence
- suite-template assignments
- benchmark version publication rules
- hidden/public separation
- governance metadata

### Deliverables
- seed set APIs/admin tools
- suite version publication flow
- hidden suite storage/access rules
- benchmark changelog policy

### Dependencies
WO-006, WO-008.

### Acceptance criteria
- ranked versions can be published with associated seed groups
- public APIs never leak hidden template internals
- historical versions remain replayable

### Failure conditions / notes
Do not store ranked hidden cases in frontend-consumable assets.

---

## WO-010 — Built-in Compaction Engine v1

### Objective
Implement built-in baseline methods. Algorithm sketches in `decisions.md` §B5.

### Scope
- `naive-summary` (single-call summarization baseline)
- `structured-state` (no-prose JSON-forced baseline)
- `hierarchical-summary` (chunked two-level summarization)
- `hybrid-ledger` (append-only ledger across cycles)

### Deliverables
- built-in compactor package
- method registration/catalog
- artifact normalization
- config schemas per method

### Dependencies
WO-003, WO-008.

### Acceptance criteria
- all built-ins emit canonical compaction artifact shape
- built-ins are versioned
- built-ins can be invoked by worker without special-case plumbing

### Failure conditions / notes
Do not allow any built-in to skip structured state sections. Sparse is allowed; missing schema sections are not.

---

## WO-011 — Scoring Engine v1

### Objective
Implement core correctness scoring. Weights and formulas locked in `decisions.md` §B3.

### Scope
- exact contains checks
- forbidden-value checks
- set-match checks
- normalized field checks
- rule-based continuation checks
- weighted item scoring (weights: locked_decision=3, forbidden_behavior=3, immutable_fact=2, unresolved_task=2, entity_integrity=1, planning=1)
- contradiction rate computation and penalty
- drift resistance computation
- compression ratio via cl100k tokenizer
- case/run aggregation

### Deliverables
- `packages/scoring-engine`
- scorecard generation
- metrics catalog
- deterministic test suite

### Dependencies
WO-003, WO-008.

### Acceptance criteria
- scorer can evaluate generated evaluation items against model responses
- per-item, per-case, and per-run scorecards are produced
- contradiction and compression metrics are computed

### Failure conditions / notes
Do not start with opaque judge-only scoring. Exact and structured checks must be primary.

---

## WO-012 — Model Provider Abstraction and First Provider Integration

### Objective
Create a clean model provider client layer and integrate the v1 providers from `decisions.md` §A2.

### Scope
- provider abstraction
- request/response normalization
- timeout/retry policy (respects provider 429 with exponential backoff)
- provider config storage
- Groq integration (primary): Llama 3.3 70B, Kimi K2 Instruct
- Google AI Studio integration (secondary): Gemini 2.0 Flash
- Ollama integration (local dev): Llama 3.2
- deterministic mock provider (tests)

### Deliverables
- provider client package (`packages/provider-clients`)
- provider config model with bootstrap rows per `decisions.md` §A2
- worker integration path
- mock provider for local dev/tests

### Dependencies
WO-001, WO-003.

### Acceptance criteria
- worker can execute baseline and compacted evaluation prompts against provider
- provider failures are typed and recoverable where appropriate
- local mock provider exists

### Failure conditions / notes
Do not hardcode provider details deep in worker jobs.

---

## Phase 2 — Execution pipeline and custom methods

---

## WO-013 — Experiment Orchestrator and Queue Model

### Objective
Create the job graph for runs.

### Scope
- run creation -> orchestration fanout
- case generation jobs
- compaction jobs
- evaluation jobs
- scoring jobs
- aggregation jobs
- cancellation handling

### Deliverables
- orchestration module
- job contracts
- status transitions
- retry policy

### Dependencies
WO-004 through WO-012.

### Acceptance criteria
- a new run expands into case-level jobs
- status transitions are valid and replay-safe
- run cancellation stops future work cleanly

### Failure conditions / notes
No synchronous long-running execution in API request path.

---

## WO-014 — Worker Execution Pipeline

### Objective
Implement actual job handlers for case generation, compaction, evaluation, scoring, and aggregation.

### Scope
- queue consumers
- object storage interaction
- artifact writes
- DB status updates
- idempotency protections

### Deliverables
- worker job handlers
- run/case/cycle lifecycle updates
- artifact persistence path
- failure recovery path

### Dependencies
WO-013.

### Acceptance criteria
- full run executes end-to-end with built-in methods
- case/cycle artifacts are stored and retrievable
- retries do not duplicate published state

### Failure conditions / notes
Job handlers must be idempotent. This is not optional.

---

## WO-015 — External Callback Methods (Option C)

### Objective
Support user-hosted custom compaction methods.

### Scope
- callback endpoint config
- auth secret storage
- invocation signing/bearer support
- verification flow
- timeout policy
- response schema validation
- callback invocation logging

### Deliverables
- method verification endpoints
- callback invocation worker handler
- invocation audit records
- UI for configuring endpoint + auth

### Dependencies
WO-003, WO-014.

### Acceptance criteria
- user can configure endpoint, verify it, and run benchmarks against it
- malformed responses fail with explicit diagnostics
- secrets are encrypted and rotatable

### Failure conditions / notes
Do not accept arbitrary uploaded code in platform runtime.

---

## WO-016 — Drift Cycle Execution

### Objective
Implement repeated compact -> continue -> compact loops.

### Scope
- cycle generation
- continuation prompt generation
- cycle-level artifact persistence
- drift score computation

### Deliverables
- `run_case_cycles` pipeline
- cycle-aware result pages
- drift metrics in scorecards

### Dependencies
WO-014, WO-011, WO-012.

### Acceptance criteria
- configured cycle count executes correctly
- score degradation across cycles is measurable
- cycle artifacts are inspectable

### Failure conditions / notes
If drift is bolted on later, the system design will fight you. Build cycle-awareness into run/case models now.

---

## Phase 3 — Product surfaces

---

## WO-017 — Project Dashboard and Method Management UI

### Objective
Implement authenticated project and method surfaces.

### Scope
- project dashboard
- method list
- method creation
- built-in selection
- callback configuration
- verification history

### Deliverables
- pages from `05_page_map.md`
- API integration
- method verification UX
- error handling UX

### Dependencies
WO-005, WO-015.

### Acceptance criteria
- user can create/edit methods
- verification results are visible
- project dashboard reflects real run/method state

### Failure conditions / notes
Do not let UI invent capability or eligibility state locally.

---

## WO-018 — Run Creation Flow and Estimation UX

### Objective
Implement the run launcher flow.

### Scope
- benchmark selection
- method selection
- model selection
- execution mode
- drift cycles
- leaderboard submission toggle
- cost/time estimate surface

### Deliverables
- `/runs/new` page
- form validation
- run creation API integration
- estimate component

### Dependencies
WO-006, WO-015, WO-017.

### Acceptance criteria
- user can create runs from UI successfully
- validation is enforced server-side
- estimate is informational only, not authoritative

### Failure conditions / notes
Do not promise exact time/cost estimates. Keep them estimated and bounded.

---

## WO-019 — Results Explorer and Case Inspector

### Objective
Give users enough detail to improve methods without leaking ranked benchmark internals.

### Scope
- run summary page
- score charts
- case list
- case inspector
- cycle inspector
- export actions
- run comparison view

### Deliverables
- pages and APIs for run/result browsing
- per-case failure category rendering
- comparison UI

### Dependencies
WO-014, WO-016, WO-018.

### Acceptance criteria
- users can inspect run metrics, cases, cycles, and failure categories
- comparison view shows metric deltas
- result pages show benchmark/scorer/model/method versions

### Failure conditions / notes
Do not expose hidden ranked case payloads beyond approved visibility rules.

---

## WO-020 — Public Leaderboard v1

### Objective
Launch the public competitive surface. Ranking formula and qualification floors locked in `decisions.md` §B4.

### Scope
- leaderboard versions (segmented by benchmark version, model, and compression tier)
- publication flow
- public pages
- rank computation (elite_score: 0.40 overall + 0.30 drift + 0.20 constraint + 0.10 compression bonus)
- qualification floors (compression floor, contradiction ≤ 0.10, all cases + cycles complete, category diversity)
- tie-breakers (drift → constraint → contradiction → published_at)
- filtering
- public detail pages

### Deliverables
- public leaderboard pages
- leaderboard APIs
- publication pipeline
- baseline comparison display
- tie-breaker logic

### Dependencies
WO-011, WO-016, WO-019.

### Acceptance criteria
- public can browse leaderboard without login
- only validated platform-run results are publishable
- rank computation is reproducible
- benchmark/model/version are visible on public pages

### Failure conditions / notes
Do not open leaderboard publication before anti-gaming gates exist.

---

## WO-021 — Billing, Quotas, and Plan Gating

### Objective
Add monetization and protect infrastructure. Plan tiers locked in `decisions.md` §B10.

### Scope
- billing account model
- Stripe checkout/portal integration (per `decisions.md` §A7)
- usage ledger
- quota enforcement (limits from `decisions.md` §B7)
- plan gating on suites, runs, exports, and callback usage

### Deliverables
- billing pages
- usage API
- quota middleware/rules
- Stripe webhooks

### Dependencies
WO-002, WO-013, WO-019.

### Acceptance criteria
- paid plans can be purchased and managed
- quotas are enforced server-side
- free plan cannot bypass run limits or elite access rules

### Failure conditions / notes
Backend owns quotas. Never trust UI plan checks.

---

## Phase 4 — Elite hardening and launch readiness

---

## WO-022 — Elite Benchmark Program

### Objective
Build the flagship benchmark program described in `07_elite_benchmark_program.md`. Launch families and case counts locked in `decisions.md` §B6; compression floors in §B9.

### Scope
- Elite Practice (5 public variations per family)
- Elite Ranked (20 hidden variations per family)
- launch families: `buried_constraint_v1`, `decision_override_v1`, `entity_confusion_v1`
- seed policy
- category balance
- compression tier thresholds (Elite-Light 2×, Elite-Mid 4×, Elite-Aggressive 8×)
- version governance

### Deliverables
- elite suite catalog entries
- elite template families
- hidden ranked seed groups
- governance docs and admin controls

### Dependencies
WO-008, WO-009, WO-011, WO-016.

### Acceptance criteria
- Elite Ranked exists as a hidden, generated, versioned program
- Elite public practice mode exists separately
- leaderboard can rank Elite-qualified runs
- compression threshold policy is enforced

### Failure conditions / notes
Do not represent Elite as a static fixed test. That is how it gets gamed.

---

## WO-023 — Leaderboard Anti-Gaming Controls

### Objective
Protect leaderboard integrity.

### Scope
- hidden/public split enforcement
- compression qualification floors
- suspicious-run heuristics
- replay / requalification hooks
- rate limiting for repeated submissions
- shadow evaluation hooks for top methods

### Deliverables
- anti-gaming rule set
- leaderboard qualification service
- moderation/admin tools
- suspicious entry review UI or admin action path

### Dependencies
WO-020, WO-022.

### Acceptance criteria
- leaderboard rejects runs that fail qualification floors
- suspicious runs can be flagged or withheld from publication
- repeated spam submissions are rate-limited

### Failure conditions / notes
A leaderboard without anti-gaming controls is worse than no leaderboard.

---

## WO-024 — Export and Report Generation

### Objective
Let users export credible run artifacts and reports.

### Scope
- PDF report
- CSV summaries
- JSON export
- signed download URLs
- export history

### Deliverables
- export worker jobs
- export endpoints
- export UI
- artifact retention rules

### Dependencies
WO-019.

### Acceptance criteria
- users can generate and download reports
- exports include version metadata
- export generation is async and resilient

### Failure conditions / notes
Never omit benchmark/scorer/model/method versions from exports.

---

## WO-025 — Observability, Audit, and Admin Diagnostics

### Objective
Harden the platform operationally before launch.

### Scope
- structured logs
- metrics
- traces
- audit logs
- admin deep-run diagnostics
- replay/recompute tools
- provider outage handling

### Deliverables
- observability dashboards
- admin diagnostics pages
- replay commands
- runbooks

### Dependencies
WO-014 onward.

### Acceptance criteria
- platform operators can diagnose failed runs
- replay is possible without corrupting history
- provider or callback outages are visible quickly

### Failure conditions / notes
If you cannot debug failed ranked runs, trust collapses fast.

---

## WO-026 — Security Hardening and Abuse Controls

### Objective
Close obvious launch-time security and abuse gaps.

### Scope
- secret encryption and rotation
- callback request signing
- rate limiting
- IP/device heuristics as needed
- artifact access control
- public/private publication boundaries
- data retention enforcement

### Deliverables
- security checklist
- abuse controls
- secret rotation workflows
- access-control test coverage

### Dependencies
WO-015, WO-020, WO-025.

### Acceptance criteria
- secrets are encrypted at rest
- callback invocations are authenticated
- private artifacts are not publicly retrievable
- abusive submission patterns can be throttled

### Failure conditions / notes
Do not ship a public leaderboard backed by weak artifact and secret boundaries.

---

## WO-027 — CI/CD, Staging, Production Deployments, and Backups

### Objective
Prepare the platform to ship safely.

### Scope
- CI pipeline completion
- staging deployment
- production deployment
- DB migration process
- backup and restore policy
- smoke tests
- rollback procedure

### Deliverables
- deploy pipelines
- infra config
- backup jobs
- restore drill docs
- release runbook

### Dependencies
WO-001 and all launch-critical domains.

### Acceptance criteria
- platform can be deployed to staging and production repeatably
- migrations are safe and reversible
- backups and restore are tested
- post-deploy smoke tests cover run creation, execution, scoring, and leaderboard read paths

### Failure conditions / notes
No launch without tested restore procedures.

---

## WO-028 — Launch Readiness, QA, and Controlled Rollout

### Objective
Finish validation and launch in a controlled way.

### Scope
- end-to-end QA matrix
- plan and quota validation
- benchmark integrity checks
- leaderboard publication checks
- legal/privacy copy review
- controlled rollout plan

### Deliverables
- launch checklist
- QA report
- controlled rollout strategy
- first benchmark version freeze
- first leaderboard version freeze

### Dependencies
All prior workorders.

### Acceptance criteria
- all critical flows pass QA
- first leaderboard version is frozen and documented
- first Elite Ranked version is frozen and documented
- rollback and moderation plans exist

### Failure conditions / notes
Do not keep changing benchmark/scoring formulas during launch week.

## Suggested phase summary

### Phase 0
WO-001 through WO-005

### Phase 1
WO-006 through WO-012

### Phase 2
WO-013 through WO-016

### Phase 3
WO-017 through WO-021

### Phase 4
WO-022 through WO-028

## Final delivery recommendation

Build in this order:

1. benchmark truth
2. scoring truth
3. execution pipeline
4. custom callback interface
5. results explorer
6. leaderboard
7. Elite program
8. launch hardening

That order protects the product from turning into a thin UI on weak benchmark logic.
