# 09. Technical Decisions — Locked for v1

## Status

- **Version**: 1.0
- **Date locked**: 2026-04-16
- **Owner**: k@shipleed.com
- **Scope**: All decisions here are the authoritative reference for WO-001 through WO-028.
- **Budget constraint**: zero third-party spend at v1. Every choice below fits a free tier, free forever-tier, or self-hosted free software.

This document is the source of truth for platform choices, schemas, formulas, and policy numbers. Where earlier documents (`01_architecture_overview.md`, `02_repo_structure.md`, `04_api_endpoints.md`, `08_workorders_bootstrap_to_launch.md`) say "recommended" or leave a choice open, this document overrides them.

---

## Part A — Platform stack

### A1. Authentication

**Decision**: ASP.NET Core Identity, with:

- cookie-based session auth for the web app
- JWT bearer auth for API clients (phase 2)
- external OAuth providers: Google and GitHub (sign-in only, no social import)
- email/password signup with email verification
- password reset via email token

**Rationale**: free, .NET-native, maps cleanly to the `users` table from `03_database_schema.md`. No vendor lock, no per-MAU cost.

**Rejected alternatives**:
- Clerk / Auth0 / Supabase Auth — all push to paid tier on growth
- Custom JWT from scratch — reinvents solved problem

**Implementation notes**:
- Store users in existing Postgres `users` table; extend with Identity columns (`password_hash`, `security_stamp`, etc.)
- External-login table records Google/GitHub account links
- Cookies set `Secure`, `HttpOnly`, `SameSite=Lax`
- CSRF tokens required on all non-GET requests
- Enforce `email_verified_at IS NOT NULL` before project creation

### A2. Model providers

**Primary (benchmark execution)**: Groq, Llama 3.3 70B and Kimi K2 Instruct
**Secondary (fallback / provider redundancy)**: Google AI Studio, Gemini 2.0 Flash
**Local development**: Ollama running Llama 3.2 locally
**Tests**: deterministic mock provider in `packages/provider-clients`

**Rationale**: Groq's free tier has enough daily requests for a private-beta workload; Gemini's free tier adds a second independent provider for rate-limit headroom and drift comparison. Both are free in 2026. Anthropic and OpenAI are deferred — the platform abstracts providers so switching is a configuration change.

**Provider config table rows at bootstrap**:
| provider_key | model_key | status |
|---|---|---|
| groq | llama-3.3-70b-versatile | active |
| groq | kimi-k2-instruct | active |
| google-ai-studio | gemini-2.0-flash | active |
| ollama-local | llama-3.2 | active (local-only) |
| mock | deterministic-mock | active (test-only) |

**First leaderboard version pins**: Groq + Llama 3.3 70B. Second leaderboard version: Gemini 2.0 Flash. Each model gets its own leaderboard segmentation per §10 of `01_architecture_overview.md`.

**Rate limit expectations** (applied in `provider-clients`):
- Groq free: ~30 req/min, ~14,400 req/day per key — enough for ~5 full runs/day at v1 case counts
- Google AI Studio free: 15 req/min, 1,500 req/day
- Workers must respect provider-reported 429s with exponential backoff

### A3. Queue

**Decision**: Hangfire with Postgres job storage.

**Rationale**: .NET-native, free, Postgres-backed (no separate Redis persistence for jobs), built-in dashboard for operator inspection. The `experiment orchestrator` module from §5.3 of `01_architecture_overview.md` becomes Hangfire recurring/background jobs; the `worker service` consumes them.

**Redis role**: caching and rate limiting only. Not job storage.

**Rejected alternatives**:
- BullMQ — requires Node worker, conflicts with .NET worker stack
- MassTransit — heavier than v1 needs
- Custom Postgres-backed queue — Hangfire already does this correctly

### A4. Object storage

**Local + v1 production**: MinIO (self-hosted, single-binary, S3-compatible).
**Post-scale migration target**: Cloudflare R2 (10 GB free + zero egress fees).

**Rationale**: MinIO is free and S3-API compatible, so provider-clients switch to R2/S3 via config change only. AWS S3 egress fees make it unsuitable until revenue exists.

**Buckets at bootstrap**:
- `compactionbench-artifacts` — transcripts, compacted artifacts, model responses
- `compactionbench-exports` — generated PDF/CSV/JSON exports
- `compactionbench-hidden` — hidden ranked benchmark content (access-restricted)

All objects encrypted at rest; keys managed by env variable at v1 (rotate into a KMS when budget allows).

### A5. Hosting

**v1 production**: Oracle Cloud Free Tier — 2 AMD VMs (1 OCPU / 1 GB each) or 1 Ampere VM (4 OCPU / 24 GB) + 200 GB block storage + 10 TB egress/month, forever free.
**Edge**: Cloudflare free plan for DNS, CDN, TLS, DDoS protection.
**Backup**: nightly pg_dump + MinIO bucket sync to a second Oracle VM or Cloudflare R2.

**Deployment**: Docker Compose on a single Ampere VM, per the compose file in `02_repo_structure.md`. Migrate to proper container orchestration when revenue justifies it.

**Staging**: a second Oracle free-tier VM, identical stack.

**Rejected alternatives**:
- Fly.io free tier — smaller resource ceiling
- Railway / Render — free tiers have sleeping or usage caps that break worker jobs

### A6. Frontend stack

**Framework**: Next.js 15 with App Router + React 19
**Styling**: Tailwind CSS
**Components**: shadcn/ui (copy-paste, owned in-repo) + Radix primitives
**Icons**: lucide-react
**Charts**: Recharts (drift curves, score breakdowns, leaderboard histograms)
**Data fetching**: TanStack Query + typed client generated from OpenAPI
**Forms**: react-hook-form + Zod validation

**Rationale**: all free, all industry-standard in 2026, no UI vendor lock.

### A7. Billing

**Decision**: Stripe — deferred integration until WO-021.

**v1 private beta**: plan entitlements hardcoded in `packages/common/plans.ts`. No billing UI shipped.

**Rationale**: Stripe has no monthly fee, only 2.9% + $0.30 per transaction. Free to integrate. Deferring until WO-021 keeps the critical path to first benchmark shorter.

### A8. Email

**v1 production**: Resend free tier (3,000 emails/month, requires domain verification).
**Local development**: MailDev (Docker container, catches all SMTP traffic in a browser UI).

**Volume estimate**: signup confirmations + invite emails + leaderboard publication notices. Fits free tier comfortably through private beta.

**Domain**: purchase one `.com` or `.io` at ~$12/year. This is the only post-launch cash cost.

**Templates to ship at WO-002**:
- email verification
- password reset
- team invite
- (post-WO-021) leaderboard publication confirmation

### A9. .NET version

**Decision**: .NET 10 (LTS, released November 2025, support through November 2028).

**Upgrade path from spec**: earlier documents reference .NET 8. Treat all ".NET 8" mentions as ".NET 10."

**Rationale**: .NET 8 LTS ends November 2026; shipping on it would require an immediate upgrade. .NET 10 is the current LTS.

### A10. Supporting tooling (all free)

| Concern | Tool | Notes |
|---|---|---|
| Version control | Git + GitHub (private repo) | free for private with unlimited collaborators |
| CI/CD | GitHub Actions | 2,000 min/month free for private repos |
| .NET testing | xUnit + FluentAssertions + Testcontainers | integration tests spin real Postgres |
| Frontend testing | Vitest + React Testing Library | unit/component |
| End-to-end testing | Playwright | browser flows |
| Load testing | k6 | scripted against staging |
| DB migrations | EF Core migrations | per-service migration bundles |
| API documentation | built-in ASP.NET OpenAPI + Scalar UI | free, self-hosted |
| Logging | Serilog → OpenTelemetry | structured logs |
| Metrics | Prometheus + Grafana (self-hosted) | on same Oracle VM |
| Tracing | Tempo (self-hosted) | part of Grafana LGTM stack |
| Log aggregation | Loki (self-hosted) | part of Grafana LGTM stack |
| Error tracking | Sentry free tier | 5,000 events/month |
| Uptime monitoring | Uptime Kuma (self-hosted) or Better Stack free tier | 10 monitors free |
| Secret management | env vars at v1; migrate to HashiCorp Vault OSS when multi-node | no cloud secret manager cost |
| Container registry | GitHub Container Registry | free for public, private on Actions plan |

---

## Part B — Product content

### B1. Benchmark template DSL

**Decision**: YAML templates, Handlebars-style `{{variable}}` substitution, JSON Schema validation of the template file itself, deterministic PRNG driving all generators.

**Canonical structure**:

```yaml
template:
  key: buried_constraint_v1
  family: buried_constraint
  version: 1.0.0

  difficulty_policy:
    distractor_turns:
      easy: 5
      medium: 10
      hard: 20
      elite: 40
    paraphrase_depth:
      easy: 0
      medium: 1
      hard: 2
      elite: 3
    override_timing:
      easy: early
      medium: mid
      hard: late
      elite: very_late

  variables:
    - name: entity
      generator: person_name
    - name: forbidden_action
      generator: action_phrase
    - name: project_topic
      generator: project_noun

  transcript:
    turns:
      - role: user
        template: "Let's plan {{entity}}'s {{project_topic}}."
      - role: assistant
        template: "Happy to. What constraints should I keep in mind?"
      - role: user
        template: "Important: never {{forbidden_action}}. That's non-negotiable."
        tags: [critical_constraint]
      - role: distractor_block
        count: "{{difficulty.distractor_turns}}"

  ground_truth:
    immutable_facts:
      - "entity:{{entity}}"
      - "topic:{{project_topic}}"
    locked_decisions: []
    forbidden_behaviors:
      - "{{forbidden_action}}"
    entity_map:
      "{{entity}}": primary_subject

  evaluation_items:
    - key: recall_constraint
      type: constraint_recall
      prompt: "What did the user say must never happen?"
      expected:
        check: contains_normalized
        value: "{{forbidden_action}}"
    - key: apply_constraint
      type: planning
      prompt: "Propose the next step for {{entity}}'s {{project_topic}}."
      expected:
        check: forbidden_absent
        value: "{{forbidden_action}}"
```

**Parser location**: `packages/benchmark-dsl`.
**Seeded generators**: `person_name`, `action_phrase`, `project_noun`, `date_iso`, `amount_usd`, `product_sku`, `org_name`. Each draws from a bounded lexicon and advances a seeded PRNG. Same seed → same output, always.

### B2. Compaction artifact JSON Schema

**Decision**: strict schema, every section required (empty arrays allowed, missing keys rejected).

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://compactionbench.dev/schemas/compaction-artifact-v1.json",
  "type": "object",
  "required": [
    "schemaVersion",
    "summaryText",
    "structuredState",
    "selectedSourceTurnIds",
    "warnings",
    "methodMetadata"
  ],
  "additionalProperties": false,
  "properties": {
    "schemaVersion": { "const": "1.0.0" },
    "summaryText": { "type": "string", "maxLength": 8000 },
    "structuredState": {
      "type": "object",
      "required": [
        "immutable_facts",
        "locked_decisions",
        "deferred_items",
        "forbidden_behaviors",
        "entity_map",
        "unresolved_items"
      ],
      "additionalProperties": false,
      "properties": {
        "immutable_facts":     { "type": "array", "items": { "type": "string", "maxLength": 500 }, "maxItems": 200 },
        "locked_decisions":    { "type": "array", "items": { "type": "string", "maxLength": 500 }, "maxItems": 200 },
        "deferred_items":      { "type": "array", "items": { "type": "string", "maxLength": 500 }, "maxItems": 200 },
        "forbidden_behaviors": { "type": "array", "items": { "type": "string", "maxLength": 500 }, "maxItems": 200 },
        "entity_map":          { "type": "object", "additionalProperties": { "type": "string", "maxLength": 200 }, "maxProperties": 200 },
        "unresolved_items":    { "type": "array", "items": { "type": "string", "maxLength": 500 }, "maxItems": 200 }
      }
    },
    "selectedSourceTurnIds": { "type": "array", "items": { "type": "integer", "minimum": 0 } },
    "warnings": { "type": "array", "items": { "type": "string", "maxLength": 500 }, "maxItems": 50 },
    "methodMetadata": { "type": "object" }
  }
}
```

**Validation enforcement**:
- API validates on ingest from external callback
- Worker validates on built-in compactor output
- Schema violations fail the case cycle; retry with same inputs is disabled until method is fixed
- `maxResponseBytes`: 256 KB for callback responses

### B3. Scoring formulas

**Per-item score**: boolean pass/fail (`{0, 1}`) for exact/structural checks; graded `[0, 1]` for rubric checks.

**Item weights** (by `item_type`):

| item_type | weight |
|---|---|
| `locked_decision_retention` | 3 |
| `forbidden_behavior_retention` | 3 |
| `immutable_fact_recall` | 2 |
| `unresolved_task_continuity` | 2 |
| `entity_integrity` | 1 |
| `planning_soundness` | 1 |

**Case-cycle score**:

```
cycle_score = sum(weight_i * item_score_i) / sum(weight_i)
```

**Contradiction rate** (per cycle):

```
contradiction_rate =
  count(responses violating a locked_decision OR forbidden_behavior)
  / count(total responses in cycle)
```

**Penalized cycle score**:

```
penalized_cycle_score = cycle_score * (1 - contradiction_rate)
```

**Drift resistance** (per case):

```
drift_delta_n = cycle_score_n - cycle_score_0   for n in [1 .. drift_cycle_count]
drift_resistance = clamp(1 + mean(drift_delta_n), 0, 1)
```

A method that holds steady across cycles scores 1.0. A method that degrades by 20% per cycle scores below 1.0 proportionally.

**Compression ratio**:

```
compression_ratio =
  tokens(original_transcript)
  / (tokens(summaryText) + tokens(serialize(structuredState)))
```

Tokenizer: cl100k tiktoken as canonical reference regardless of target model. This makes compression comparable across boards.

**Case overall**: mean of penalized cycle scores (uniform weighting for v1; drift-weighted variants deferred).

**Run overall**: mean of case overall scores.

### B4. Leaderboard ranking formula

**Elite score** (what the board sorts by):

```
elite_score =
    0.40 * run_overall_score
  + 0.30 * drift_resistance
  + 0.20 * constraint_retention
  + 0.10 * compression_bonus

where:
  constraint_retention = mean(
    pass_rate(locked_decision_retention),
    pass_rate(forbidden_behavior_retention)
  )

  compression_bonus = clamp(
    (compression_ratio - tier_floor) / tier_floor,
    0, 1
  )
```

**Tie-breakers** (in order): higher `drift_resistance` → higher `constraint_retention` → lower `contradiction_rate` → earlier `published_at`.

**Qualification floors** (all must pass):

- `compression_ratio >= tier_floor` (see B9)
- `contradiction_rate <= 0.10`
- all configured case slots completed (no `failed` or `cancelled` cases)
- all configured drift cycles completed (v1: 2 cycles)
- no single benchmark family below 0.40 case-level pass rate (category-diversity guard)
- no callback or scoring failures in ranked slots
- no suspicious-replay flags from admin review

### B5. Built-in compactor algorithms

All four emit the artifact schema from B2. All four registered at bootstrap.

**1. `naive-summary` (baseline)**
- Single LLM call with prompt: "Summarize the following conversation in ≤500 words. Preserve all constraints, decisions, and unresolved items."
- Output → `summaryText`
- Structured state sections all empty arrays / empty object
- Purpose: baseline showing what *not* to do; dominated by every other method on structured metrics

**2. `structured-state` (no-prose baseline)**
- Single LLM call with JSON-schema-forced output populating all six structured sections
- `summaryText` empty string
- `selectedSourceTurnIds` = turns referenced in extraction

**3. `hierarchical-summary`**
- Chunk transcript into 10-turn windows
- Summarize each window (first-level summaries)
- Summarize the first-level summaries (second-level)
- Concatenate second-level into `summaryText`
- Separate extraction call populates `structuredState`

**4. `hybrid-ledger` (expected strongest baseline)**
- Maintains an append-only ledger across cycles: `locked_decisions`, `forbidden_behaviors`, and `unresolved_items` accumulate; compaction adds to them rather than rewriting
- `summaryText` is 2–3 sentences of situational framing
- `immutable_facts` and `entity_map` rebuilt per cycle from transcript
- Ledger state flows between cycles via `methodMetadata.previous_ledger` (opaque to the scorer)

### B6. Initial Elite template coverage

Ship **3 families at v1 launch**, each with 20 hidden ranked seed variations and 5 public practice variations. Expand after launch.

| Family | v1 | Rationale |
|---|---|---|
| `buried_constraint_v1` | yes | canonical constraint-preservation test |
| `decision_override_v1` | yes | late-override retention |
| `entity_confusion_v1` | yes | similar-entity discrimination |
| `negative_rule_v1` | post-launch | |
| `exception_precedence_v1` | post-launch | |
| `resolved_vs_unresolved_v1` | post-launch | |
| `stale_summary_poison_v1` | post-launch | |
| `cross_session_state_v1` | post-launch | |
| `drift_decay_v1` | post-launch | |
| `conflicting_hypotheses_v1` | post-launch | |
| `numeric_near_collision_v1` | post-launch | |
| `time_order_inversion_v1` | post-launch | |
| `policy_exception_tree_v1` | post-launch | |
| `alias_resolution_v1` | post-launch | |
| `scope_rejection_persistence_v1` | post-launch | |

**Launch case counts**:
- Starter public suite: 20 cases
- Hard public suite: 30 cases
- Elite Ranked hidden: 60 cases (20 per family)
- Elite Practice public: 15 cases (5 per family)

### B7. Rate limits

| Surface | Free | Pro | Team |
|---|---|---|---|
| Public API (per IP) | 60/min | 60/min | 60/min |
| Authenticated API | 600/min | 600/min | 600/min |
| Run creation | 5/hour | 50/hour | 500/hour |
| Leaderboard submission | 1/day per method per version | same | same |
| External callback invocation timeout | 30 s | 30 s | 30 s |
| External callback max response size | 256 KB | 256 KB | 256 KB |
| Callback retries | 3 | 3 | 3 |
| Retry backoff | exponential 2^n seconds (2, 4, 8) | same | same |

### B8. Retention

| Data | Free plan | Paid plan |
|---|---|---|
| Private transcripts & model responses | 90 days | 365 days |
| Callback invocation bodies (sanitized) | 90 days | 90 days |
| Leaderboard snapshots | permanent | permanent |
| Audit logs | 365 days | 365 days |
| Hidden ranked case artifacts | 180 days hot → cold archive | same |
| Exports | 30 days | 90 days |

After hot retention expires, artifact blobs are deleted from object storage; DB rows retain metadata.

### B9. Compression tier floors

| Tier | Minimum compression ratio |
|---|---|
| Elite-Light | 2.0× |
| Elite-Mid | 4.0× |
| Elite-Aggressive | 8.0× |
| Starter public | no floor (compression ranked, not gated) |
| Hard public | no floor |

Leaderboard segments by tier — aggressive-compression methods never compete directly against light-compression methods.

### B10. Pricing tiers (activated at WO-021)

| Tier | Price | Projects | Runs/mo | Elite ranked | Leaderboard submission | Callback endpoints |
|---|---|---|---|---|---|---|
| Free | $0 | 3 | 20 | practice only | view only | 1 |
| Pro | $49/mo | 10 | 200 | yes | yes | 5 |
| Team | $149/mo | 50 | 1,000 | yes | yes (org name displayed) | 20 |
| Enterprise | custom | unlimited | custom | yes | priority queue | custom |

All tiers: 2 drift cycles for leaderboard qualification; export access included.

---

## Part C — Docker Compose service map

Canonical local-dev stack (lives in `docker-compose.yml`):

| Service | Image / source | Port | Purpose |
|---|---|---|---|
| `web` | local build of `apps/web` | 3000 | Next.js app |
| `api` | local build of `apps/api` | 5000 | ASP.NET Core API |
| `worker` | local build of `apps/worker` | — | .NET worker |
| `postgres` | `postgres:17-alpine` | 5432 | primary DB |
| `redis` | `redis:7-alpine` | 6379 | cache + rate-limit counters |
| `minio` | `minio/minio:latest` | 9000, 9001 | S3-compatible storage |
| `maildev` | `maildev/maildev` | 1080, 1025 | local SMTP + web UI |
| `ollama` | `ollama/ollama` | 11434 | local model provider |
| `mock-provider` | local build | 5050 | deterministic model mock |
| `mock-callback` | local build | 5060 | sample external callback endpoint |
| `hangfire-dashboard` | served from `api` | 5000/hangfire | job inspection |
| `prometheus` | `prom/prometheus` | 9090 | metrics (dev-optional) |
| `grafana` | `grafana/grafana` | 3001 | dashboards (dev-optional) |

---

## Part D — Deferred decisions

Explicitly not decided at v1 lock; revisit post-launch.

- **Paid model providers** (Anthropic Claude, OpenAI GPT, Google Vertex AI): integration after revenue justifies spend.
- **Elite template families 4–15**: content roadmap, one family added per month post-launch.
- **SSO / SAML**: Enterprise tier feature, not v1.
- **Custom KMS / secret manager**: env vars v1; HashiCorp Vault OSS when infra grows beyond one VM.
- **Managed Postgres**: self-hosted on Oracle VM v1; move to Neon / Supabase / RDS when operational burden warrants.
- **Proper CDN for artifacts**: Cloudflare free plan covers v1 static; add R2 when bandwidth grows.
- **Shadow evaluation automation** (Elite §5.3): manual admin trigger v1; scheduled automation when top-method density justifies it.
- **Multi-region deployment**: single-region v1.
- **Mobile app / native clients**: not v1.

---

## Part E — Total budget

| Cost | Amount |
|---|---|
| Auth, DB, queue, storage, hosting, CI, monitoring, email | $0 |
| Domain name (required for Resend and public leaderboard) | ~$12/year |
| **v1 launch total** | **~$12/year** |

Everything else comes out of future revenue.

---

## Revision history

| Version | Date | Change |
|---|---|---|
| 1.0 | 2026-04-16 | initial lock |
