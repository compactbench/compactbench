# 06. Service Responsibilities

## 1. Responsibility split principle

Each service/module must have a narrow, defensible ownership boundary.

Do not allow:
- frontend business logic drift
- benchmark generation scattered across API and worker
- scoring logic duplicated in UI
- leaderboard ranking calculated ad hoc in controllers

## 2. Service inventory

## 2.1 Web application
Owns:
- rendering pages
- auth UX
- client-side form handling
- query caching
- user-facing charts/tables
- public pages

Does not own:
- benchmark generation
- scoring
- leaderboard eligibility
- quota enforcement
- security decisions

## 2.2 API backend
Owns:
- authenticated request validation
- user/team/project CRUD
- method CRUD
- benchmark catalog exposure
- run creation
- quota enforcement
- export requests
- leaderboard publication commands
- admin command surface
- audit log creation

Does not own:
- case generation execution
- model inference
- callback execution loops
- scoring execution
- ranking recomputation jobs

## 2.3 Experiment orchestrator
Owns:
- run fanout
- job graph planning
- seed set allocation
- case slot expansion
- drift cycle scheduling
- retry-safe orchestration state

Does not own:
- actual model inference
- storage of raw blobs beyond references
- leaderboard publication rules themselves

## 2.4 Worker service
Owns:
- benchmark generation execution
- built-in compaction execution
- external callback invocation
- model provider execution
- scoring execution
- artifact writes
- run aggregation handoff

Does not own:
- project/method CRUD
- permission decisions
- public query APIs

## 2.5 Benchmark engine
Owns:
- template parsing
- deterministic generation
- transcript creation
- ground-truth construction
- evaluation item generation
- difficulty knobs

Does not own:
- DB access policy
- HTTP routing
- leaderboard formulas

## 2.6 Scoring engine
Owns:
- exact checks
- normalized field checks
- rule-based checks
- score aggregation
- contradiction penalty calculation
- drift degradation calculations

Does not own:
- benchmark generation
- leaderboard publication records
- frontend visualization

## 2.7 Built-in compactors package
Owns:
- built-in method implementations
- built-in method versions
- artifact normalization

Does not own:
- project-specific configuration storage
- callback execution
- scoring

## 2.8 Provider client package
Owns:
- model provider request formatting
- timeout/retry policy
- response normalization
- provider error typing

Does not own:
- benchmark generation
- scoring
- public API concerns

## 2.9 Leaderboard core
Owns:
- eligibility checks
- rank calculation
- tie-breakers
- minimum score floors
- publication snapshots

Does not own:
- raw evaluation execution
- case generation
- artifact storage

## 2.10 Object storage adapter
Owns:
- artifact upload/download/delete
- signed URL generation if needed
- encryption metadata handling

Does not own:
- benchmark semantics
- scoring

## 2.11 Billing adapter
Owns:
- checkout session creation
- portal session creation
- webhook reconciliation
- plan entitlements projection

Does not own:
- run creation logic
- leaderboard logic

## 2.12 Admin module
Owns:
- suite/template admin operations
- hidden benchmark controls
- leaderboard moderation
- provider configuration
- replay/recompute commands

Does not own:
- end-user project flows

## 3. Domain ownership map

## 3.1 Identity and tenancy
Primary owner:
- API backend

## 3.2 Benchmark definitions
Primary owner:
- benchmark engine + admin module

## 3.3 Run execution
Primary owner:
- orchestrator + worker

## 3.4 Scoring and metrics
Primary owner:
- scoring engine

## 3.5 Public ranking
Primary owner:
- leaderboard core + API publication layer

## 3.6 Results exploration
Primary owner:
- API backend for data shape, web for rendering

## 4. Failure-domain guidance

## 4.1 Callback failures
If a user callback endpoint fails:
- case cycle fails or retries based on policy
- run may become partial_failed
- API remains healthy
- leaderboard publication is blocked if qualification incomplete

## 4.2 Provider failures
If model provider fails:
- worker retries where safe
- run status reflects provider issue
- no partial silent success

## 4.3 Scoring failures
If scoring fails:
- do not publish leaderboard results
- keep raw artifacts for replay
- mark run not final

## 4.4 Admin mistakes
If a bad benchmark version is published:
- version it
- retire it
- do not mutate historical results invisibly

## 5. Ownership boundaries that matter most

### Boundary 1: frontend vs backend
Backend owns:
- validation
- authorization
- quota
- eligibility
- score truth

Frontend only renders and submits commands.

### Boundary 2: API vs worker
API owns:
- control plane
- persistence of commands/metadata
- permissions

Worker owns:
- execution plane
- expensive and retryable workloads

### Boundary 3: benchmark engine vs scoring engine
Benchmark engine defines truth cases.
Scoring engine measures responses against truth.

Do not blur them.

### Boundary 4: private results vs public leaderboard
Public leaderboard should be a projection of validated run results, not a separate scoring system.

## 6. Service-to-service interaction summary

### Web -> API
- synchronous HTTP

### API -> Redis / Queue
- enqueue orchestration and exports

### Worker -> DB/Object storage
- heavy write path

### Worker -> model providers
- outbound network

### Worker -> user callback endpoints
- outbound network with strict policy

### API -> object storage
- read/download metadata and signed URLs

## 7. Monitoring ownership

### API
- request latency
- auth failures
- permission failures
- rate limiting
- 5xx budget

### Worker
- job latency
- retry counts
- callback failures
- provider failures
- scoring failures

### Benchmark/scoring modules
- determinism regression tests
- version mismatch alerts
- formula drift alerts

### Leaderboard
- publication queue
- rank recomputation anomalies
- suspicious submission patterns

## 8. Final service-responsibility verdict

The clean split is:

- **web**: presentation
- **api**: control plane
- **worker**: execution plane
- **benchmark engine**: benchmark truth generation
- **scoring engine**: correctness measurement
- **leaderboard core**: public ranking logic

Keep those boundaries hard. If they blur, the platform will become difficult to trust and difficult to evolve.
