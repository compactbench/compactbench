# 02. Repository Structure

## 1. Repo strategy

Use a **single private monorepo**.

Reason:
- one source of truth for contracts
- easier version alignment between API, worker, and web
- easier Docker/local startup
- easier CI/CD sequencing
- easier benchmark/scoring package reuse

Do not split into multiple repos at v1. That adds coordination cost before it adds leverage.

## 2. Recommended top-level layout

```text
compactionbench/
├─ apps/
│  ├─ web/
│  ├─ api/
│  └─ worker/
├─ packages/
│  ├─ contracts/
│  ├─ benchmark-engine/
│  ├─ benchmark-dsl/
│  ├─ scoring-engine/
│  ├─ built-in-compactors/
│  ├─ leaderboard-core/
│  ├─ provider-clients/
│  ├─ common/
│  └─ frontend-sdk/
├─ infra/
│  ├─ docker/
│  ├─ compose/
│  ├─ migrations/
│  ├─ nginx/
│  ├─ scripts/
│  └─ ci/
├─ docs/
│  ├─ architecture/
│  ├─ runbooks/
│  ├─ api/
│  ├─ leaderboard/
│  └─ benchmark-governance/
├─ benchmarks/
│  ├─ public/
│  ├─ samples/
│  └─ schemas/
├─ tests/
│  ├─ unit/
│  ├─ integration/
│  ├─ e2e/
│  ├─ load/
│  └─ fixtures/
├─ tools/
│  ├─ dev-seed/
│  ├─ report-build/
│  └─ benchmark-admin/
├─ .github/
├─ docker-compose.yml
├─ docker-compose.override.yml
├─ README.md
└─ Makefile
```

## 3. App responsibilities

## 3.1 `apps/web`
Technology:
- Next.js / React

Responsibilities:
- authentication UI
- public marketing / methodology pages
- public leaderboard
- authenticated dashboard
- benchmark setup
- method management
- run launch
- results explorer
- admin pages

Notes:
- keep business logic in API/backend
- web renders and orchestrates UI only

## 3.2 `apps/api`
Technology:
- ASP.NET Core Web API on .NET 10 (LTS)
- ASP.NET Core Identity for auth
- Hangfire for background jobs (Postgres storage)

Responsibilities:
- auth/session integration
- users, teams, projects
- benchmark catalog APIs
- method CRUD
- run creation / status
- result query APIs
- leaderboard APIs
- billing and quota enforcement
- audit log creation

Notes:
- no heavy background execution
- no benchmark generation inside request path
- API is the control plane

## 3.3 `apps/worker`
Technology:
- .NET 10 worker service
- Hangfire consumer

Responsibilities:
- queue consumption
- case generation
- built-in compaction execution
- external callback invocation
- model provider execution
- scoring
- aggregation
- export generation

Notes:
- worker is the execution plane
- keep idempotent job handlers
- store artifacts early

## 4. Shared package boundaries

## 4.1 `packages/contracts`
Purpose:
- canonical DTOs
- JSON Schemas
- enum/version constants
- external callback request/response contracts

Must include:
- compaction artifact schema
- benchmark case schema
- run summary schema
- leaderboard projection schema

## 4.2 `packages/benchmark-dsl`
Purpose:
- template format
- validation
- compilation/parsing helpers
- seed policy
- template family abstractions

This package should not know about database or HTTP.

## 4.3 `packages/benchmark-engine`
Purpose:
- turn a template + seed into a case instance
- build transcript
- build ground truth
- build evaluation items
- apply difficulty policies
- apply paraphrase/noise knobs

This is one of the core product assets.

## 4.4 `packages/scoring-engine`
Purpose:
- exact checks
- structured field checks
- rule-based checks
- score normalization
- case/run aggregation

This is the second core product asset.

## 4.5 `packages/built-in-compactors`
Purpose:
- built-in compaction implementations
- versioning
- configuration defaults
- artifact normalization

Ship these first:
- naive-summary
- structured-state
- hierarchical-summary
- hybrid-ledger

## 4.6 `packages/leaderboard-core`
Purpose:
- leaderboard eligibility rules
- rank computation
- tie-breaker logic
- publication projection
- version isolation

## 4.7 `packages/provider-clients`
Purpose:
- model provider abstractions
- request/response normalization
- retry policy helpers
- rate-limit handling
- timeout handling

## 4.8 `packages/common`
Purpose:
- logging helpers
- tracing
- time utilities
- ids
- content hashing
- encryption helpers
- persistence helpers

## 4.9 `packages/frontend-sdk`
Purpose:
- typed client for web app
- generated API types
- query hooks / fetch wrappers

## 5. Benchmarks directory policy

## 5.1 `benchmarks/public`
Store only:
- public sample templates
- public practice suites
- docs examples

## 5.2 Hidden ranked benchmarks
Do **not** bundle hidden ranked templates into web assets or public benchmark exports.

Recommended policy:
- keep hidden template definitions in private admin-controlled storage and load them into DB or encrypted object storage
- optionally keep secure internal copies in a restricted repo path with strict access control
- never expose hidden benchmark content through normal API responses

## 6. Tests layout

## 6.1 Unit tests
- DSL validation
- seed determinism
- scoring rules
- compaction artifact validation
- leaderboard formula

## 6.2 Integration tests
- run creation -> worker execution -> scoring -> aggregation
- external callback happy path / timeout / malformed response
- artifact storage and retrieval
- quota enforcement

## 6.3 E2E tests
- sign in
- create project
- create method
- launch run
- inspect results
- publish leaderboard entry

## 6.4 Load tests
- leaderboard read traffic
- burst experiment creation
- callback-heavy job fanout
- worker throughput

## 7. Local development structure

## 7.1 Docker Compose services
Full service map locked in `decisions.md` §C. Summary:
- web (Next.js 15)
- api (.NET 10)
- worker (.NET 10)
- postgres 17
- redis 7
- minio (S3-compatible)
- maildev (local SMTP)
- ollama (local model provider)
- mock-provider (deterministic model mock)
- mock-callback (sample external callback)
- prometheus + grafana (dev-optional)

## 7.2 Local developer goals
- one-command startup
- seedable local benchmark fixtures
- mock provider mode to avoid spend during local dev
- no manual environment bootstrapping beyond secrets file

## 8. CI/CD structure

## 8.1 Pull request pipeline
- lint / format
- build web/api/worker
- unit tests
- integration tests
- contract/schema validation
- benchmark determinism tests
- migration validation

## 8.2 Main branch pipeline
- publish containers
- deploy staging
- run smoke tests
- optionally run controlled benchmark regression pack

## 8.3 Release pipeline
- manual approval
- migrate database
- deploy API and worker
- deploy web
- run healthchecks
- run post-deploy smoke benchmark
- monitor error budget window

## 9. Suggested documentation structure

```text
docs/
├─ architecture/
│  ├─ system-overview.md
│  ├─ data-flow.md
│  ├─ callback-contract.md
│  └─ security-model.md
├─ runbooks/
│  ├─ deploy.md
│  ├─ rollback.md
│  ├─ provider-outage.md
│  └─ leaderboard-rotation.md
├─ api/
│  ├─ public.md
│  ├─ private.md
│  └─ admin.md
├─ leaderboard/
│  ├─ methodology.md
│  ├─ ranking.md
│  └─ publication-policy.md
└─ benchmark-governance/
   ├─ elite-program.md
   ├─ template-versioning.md
   └─ hidden-suite-policy.md
```

## 10. Repo conventions

- immutable ids as UUIDs or ULIDs
- UTC timestamps everywhere
- benchmark/template/scorer/method version identifiers explicit
- backend owns logic; frontend only renders and submits commands
- JSON Schemas live in `packages/contracts`
- generated clients must be checked in only if generation is deterministic and part of build policy
- no hidden benchmark content in frontend bundle
- no hardcoded provider/model config in code

## 11. Recommended internal naming

- `Suite`: catalog-level benchmark grouping
- `Template`: generator definition
- `CaseInstance`: concrete generated case
- `Method`: compaction strategy
- `Run`: user experiment execution
- `CaseRun`: one run x one case
- `Cycle`: drift step inside a case run
- `Scorecard`: aggregated scored output
- `Entry`: public leaderboard record

## 12. Final repo verdict

Use a monorepo with strict package boundaries. Separate product assets cleanly:

- benchmark engine
- scoring engine
- built-in compactors
- leaderboard core

Those are the pieces you will evolve continuously. Keep them modular from day one.
