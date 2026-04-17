# 01. Architecture Overview

## 1. Product definition

**CompactionBench** is a managed benchmark platform for testing AI conversation compaction methods.

The platform is not a generic chatbot, prompt playground, or agent builder.

It exists to answer a narrow question:

> After replacing long conversation history with a compacted representation, does the model still behave correctly?

The platform must measure that under adversarial conditions, across multiple benchmark families, with deterministic reproducibility and public rankings.

## 2. Product promise

A user can:

- create an account
- create a project
- choose a benchmark suite and difficulty
- pick a built-in compaction method or configure an external callback method
- choose a target model
- launch an experiment
- inspect scores, drift behavior, and failure categories
- optionally submit a run to the public leaderboard

The platform owns:

- benchmark generation
- hidden benchmark management
- run orchestration
- model invocation
- scoring
- storage
- leaderboard normalization
- anti-gaming controls

## 3. Core product principles

1. **Benchmark engine first.**  
   UI, auth, billing, and leaderboard are wrappers around benchmark truth.

2. **Built-in baselines are mandatory.**  
   Users need immediate value and comparison anchors.

3. **Custom methods use external callbacks in v1.**  
   Do not run arbitrary user code in platform infrastructure at launch.

4. **Leaderboard integrity outranks convenience.**  
   A gamed leaderboard destroys the product.

5. **Randomness must be controlled.**  
   Use deterministic seeded generation, not uncontrolled per-run randomness.

6. **Scoring must reward state fidelity, not output style.**

7. **Everything material must be versioned.**  
   Benchmark suite, template, scoring profile, model, built-in method, and leaderboard version.

## 4. Recommended product shape

### 4.1 Private product surfaces

- project dashboard
- benchmark catalog
- method configuration
- run launcher
- results explorer
- run comparison
- exports

### 4.2 Public product surfaces

- public leaderboard
- public method detail pages
- public methodology page
- public benchmark overview page

### 4.3 Admin/internal product surfaces

- hidden benchmark management
- benchmark version publishing
- scorer version management
- leaderboard moderation
- abuse controls
- provider configuration
- run replay / failure inspection

## 5. High-level system architecture

### 5.1 Web application
Primary UX surface.

Responsibilities:
- auth-facing routes
- dashboard
- project flows
- run creation
- results explorer
- public leaderboard pages
- admin pages

Stack (locked in `decisions.md` §A6):
- Next.js 15 App Router + React 19
- Tailwind CSS + shadcn/ui + Radix primitives
- TanStack Query, react-hook-form, Zod, Recharts, lucide-react

### 5.2 API backend
Primary control-plane service.

Responsibilities:
- project and method CRUD
- benchmark catalog APIs
- run creation and status
- leaderboard query APIs
- billing and quota enforcement
- auth/session integration
- audit logging

Stack (locked in `decisions.md` §A9):
- ASP.NET Core on .NET 10 (LTS)
- ASP.NET Core Identity for auth (cookie sessions for web, JWT for API clients)
- Hangfire on Postgres for job scheduling

### 5.3 Experiment orchestrator
Coordinates benchmark execution.

Responsibilities:
- expand an experiment into case-level jobs
- allocate seed sets
- schedule baseline vs compacted runs
- schedule drift cycles
- aggregate case status

Can live initially inside the API or worker control plane, but treat it as a distinct module.

### 5.4 Worker service
Executes the heavy path.

Responsibilities:
- generate benchmark cases from templates
- run built-in compactors
- invoke external callback methods
- call model providers
- execute scoring
- persist artifacts

Stack (locked in `decisions.md` §A9):
- .NET 10 worker service
- Hangfire consumer for queued jobs
- provider-clients package for Groq / Google AI Studio / Ollama / mock

### 5.5 Benchmark engine
Core product module.

Responsibilities:
- template DSL
- deterministic seeded case generation
- hidden/public suite composition
- difficulty scaling
- ground-truth construction
- evaluation prompt generation

### 5.6 Scoring engine
Second core product module.

Responsibilities:
- exact checks
- structured diff checks
- rule-based continuation checks
- rubric/judge checks when required
- score normalization
- leaderboard eligibility projection

### 5.7 Leaderboard engine
Ranking and publication module.

Responsibilities:
- validate eligibility
- apply ranking formula
- enforce anti-gaming rules
- publish public projections
- isolate leaderboard by benchmark version and model

### 5.8 Storage layer
- PostgreSQL 17: metadata, run records, score summaries, leaderboard rows, Hangfire job state
- Redis 7: cache and rate-limit counters only (Hangfire owns job persistence in Postgres)
- MinIO (v1, self-hosted, S3-compatible) → Cloudflare R2 post-scale: transcripts, compacted artifacts, raw responses, exports

See `decisions.md` §A3–A4 for rationale.

## 6. Runtime data flow

### 6.1 Run creation
User selects:
- project
- benchmark suite
- difficulty
- method
- target model
- execution mode
- drift cycle count
- leaderboard submission yes/no

The API creates an `experiment_run` record and hands orchestration to the worker system.

### 6.2 Case generation
For each case slot:
- choose a benchmark template
- derive deterministic seed from benchmark version + run seed group + case slot
- generate transcript
- generate ground truth
- generate evaluation prompts/tasks
- persist case instance artifacts

### 6.3 Compaction
For each case:
- run built-in compactor or invoke external callback endpoint
- validate returned compacted artifact
- persist artifact and invocation metadata

### 6.4 Model evaluation
Run:
- full-context baseline when required
- compacted-only evaluation
- optional compacted-plus-recent-window evaluation

### 6.5 Drift cycles
If enabled:
- continue the conversation using generated continuation prompts
- compact again
- evaluate again
- repeat per configured cycle count

### 6.6 Scoring and aggregation
- compute question/task scores
- compute case-level metrics
- compute run-level aggregates
- determine leaderboard eligibility
- publish public projection if requested and valid

## 7. Benchmark model

## 7.1 Public suites
Used for:
- onboarding
- debugging
- documentation
- private experiments where transparency matters

## 7.2 Hidden suites
Used for:
- leaderboard ranking
- qualification
- anti-overfitting
- elite-ranked scoring

Users should never receive complete hidden case contents.

## 7.3 Template-based generation
Benchmarks are not static documents. They are generated from versioned templates.

Each template defines:
- structural trap type
- variable schema
- permitted paraphrase strategies
- adversarial knobs
- ground-truth assembly rules
- follow-up generation rules

## 7.4 Difficulty tiers
- Easy
- Medium
- Hard
- Elite

Difficulty changes:
- ambiguity
- paraphrase depth
- constraint overlap
- similarity of entities
- late overrides
- noise turns
- drift sensitivity

## 8. Custom method model

### 8.1 Built-in methods (Option A)
Ship at least:
- naive summary
- structured state
- hierarchical summary
- hybrid ledger

These are internal, versioned, and owned by the platform.

### 8.2 External callback methods (Option C)
User hosts their own endpoint. Platform calls it with transcript payload and expects a compacted artifact response.

Why this is the right v1 choice:
- enables real custom methods
- avoids arbitrary code execution inside the platform
- simplifies security boundary
- supports any user language/runtime

## 9. Required compaction artifact contract

Every method, built-in or external, must return the same canonical artifact shape:

- `summary_text`
- `structured_state`
- `selected_source_turn_ids`
- `warnings`
- `method_metadata`

Required structured state sections:
- immutable_facts
- locked_decisions
- deferred_items
- forbidden_behaviors
- entity_map
- unresolved_items

Do not allow arbitrary freeform output without this schema. It destroys comparability and makes scoring brittle.

## 10. Leaderboard model

The leaderboard is public and does not require registration to browse.

That is good for growth, but only if the ranking is defensible.

### 10.1 Public leaderboard requirements
- platform-run submissions only
- hidden ranked benchmark set
- deterministic seeded generation
- minimum compression threshold
- drift cycles included
- benchmark version shown
- model shown
- method version shown

### 10.2 What to publish
- rank
- method name
- organization name if opted in
- overall score
- elite score
- drift score
- constraint retention
- contradiction rate
- compression ratio
- benchmark version
- model

### 10.3 What not to publish
- hidden full test cases
- hidden prompt packs
- internal seed lists
- full scoring internals
- user secrets or raw callback config

## 11. Anti-gaming model

1. hidden benchmark sets
2. deterministic randomized case generation
3. category diversity
4. compression thresholds
5. drift cycles
6. score floor requirements
7. rate limits on leaderboard attempts
8. benchmark version rotation
9. shadow evaluations on top methods

## 12. Security model

### 12.1 Multi-tenancy
Projects belong to teams. Team boundaries are enforced server-side.

### 12.2 External callback security
- signed requests or bearer auth
- per-method secrets stored encrypted
- outbound allowlist optional later
- timeout and response size limits mandatory

### 12.3 Data privacy
Private by default. Leaderboard publication is explicit opt-in.

### 12.4 Artifact access
Raw artifacts, prompts, and transcripts stay private unless explicitly published in sanitized form.

## 13. Deployment topology

### 13.1 Core services
- web
- api
- worker
- postgres
- redis
- object storage

### 13.2 Local development
Use Docker Compose with:
- web
- api
- worker
- postgres
- redis
- local object storage emulator

### 13.3 Production
Run web, api, and worker separately. Keep API and workers private behind the edge. Public internet should only reach the web app and the public API surface it needs.

## 14. Launch slice recommendation

Ship this first:

- account creation / auth
- team + project model
- starter, hard, and elite suites (3 Elite families at launch: `buried_constraint_v1`, `decision_override_v1`, `entity_confusion_v1` — see `decisions.md` §B6)
- naive / structured / hierarchical / hybrid built-in methods
- model providers: Groq (Llama 3.3 70B, Kimi K2) + Google AI Studio (Gemini 2.0 Flash) — see `decisions.md` §A2
- external callback methods
- run orchestration
- results explorer
- public leaderboard
- hidden ranked benchmark set
- 2-cycle drift for leaderboard qualification

## 15. Key architectural risks

### Risk 1: benchmark gaming
Mitigation:
- hidden ranked cases
- deterministic seeded generation
- shadow evaluations
- version rotation

### Risk 2: noisy leaderboard
Mitigation:
- fixed benchmark version
- fixed model board segregation
- seeded fairness
- metric floor requirements

### Risk 3: callback endpoint instability
Mitigation:
- endpoint verification
- timeout policy
- retry policy
- partial failure states

### Risk 4: product drift into generic AI tooling
Mitigation:
- narrow product scope
- benchmark-first roadmap
- no arbitrary code execution at launch
- no social platform features in v1

## 16. Final architectural verdict

This platform is viable if built as a **benchmarking product**, not as a generic AI app.

The defensible core is:

- benchmark engine
- scoring engine
- built-in baselines
- external callback interface
- public leaderboard with anti-gaming controls
- Elite benchmark program that is continuously hardened and versioned
