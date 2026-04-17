# 04. API Endpoints

## 1. API design principles

- version all endpoints under `/v1`
- API is the control plane
- long-running work is async and job-backed
- request validation is strict
- responses must include benchmark, scorer, method, and model version identifiers where relevant
- do not expose hidden benchmark payloads through normal user APIs
- backend owns all validation and authorization

## 2. Authentication model

Locked in `decisions.md` §A1:
- ASP.NET Core Identity with cookie sessions for the web app
- JWT bearer auth for API clients (phase 2)
- external OAuth via Google and GitHub (sign-in only)
- email verification required before project creation
- CSRF tokens on all non-GET requests
- cookies: `Secure`, `HttpOnly`, `SameSite=Lax`

The platform owns auth end-to-end; no managed third-party auth provider at v1.

## 3. Public endpoints

## 3.1 Methodology and catalog
### `GET /v1/public/methodology`
Returns high-level public methodology:
- benchmark categories
- scoring dimensions
- leaderboard policy
- version information

### `GET /v1/public/benchmark-suites`
Returns public benchmark suite catalog summary.

Query params:
- `difficulty`
- `category`

### `GET /v1/public/benchmark-suites/{suiteKey}`
Returns public suite details:
- name
- difficulty
- public description
- version labels
- example categories
- not full hidden templates

## 3.2 Leaderboard
### `GET /v1/public/leaderboards`
Returns active leaderboard versions.

### `GET /v1/public/leaderboards/{versionKey}`
Returns ranked leaderboard rows with pagination and filters.

Query params:
- `difficulty`
- `compressionTier`
- `modelKey`
- `page`
- `pageSize`

### `GET /v1/public/leaderboards/{versionKey}/entries/{entryId}`
Returns public method score page.

Includes:
- published method/team name
- score breakdown
- category performance
- drift summary
- benchmark version
- model version

### `GET /v1/public/leaderboards/{versionKey}/stats`
Returns aggregate public stats.

## 4. Authenticated user endpoints

### `GET /v1/me`
Returns current user profile and plan context.

### `PATCH /v1/me`
Update display name, avatar, default team, and basic settings.

## 5. Team and project endpoints

## 5.1 Teams
### `GET /v1/teams`
List teams visible to current user.

### `POST /v1/teams`
Create a team.

Request:
- `name`

### `GET /v1/teams/{teamId}`
Team detail.

### `PATCH /v1/teams/{teamId}`
Update team name/settings.

### `GET /v1/teams/{teamId}/members`
List members.

### `POST /v1/teams/{teamId}/invites`
Create invite.

Request:
- `email`
- `role`

### `GET /v1/teams/{teamId}/invites`
List invites.

### `DELETE /v1/teams/{teamId}/invites/{inviteId}`
Revoke invite.

## 5.2 Projects
### `GET /v1/projects`
List projects visible to current user.

Query params:
- `teamId`
- `status`

### `POST /v1/projects`
Create project.

Request:
- `teamId`
- `name`
- `description`

### `GET /v1/projects/{projectId}`
Project detail.

### `PATCH /v1/projects/{projectId}`
Update name, description, visibility, status.

### `DELETE /v1/projects/{projectId}`
Archive or delete project depending on policy.

## 6. Benchmark catalog endpoints

### `GET /v1/benchmark-suites`
Authenticated suite catalog.

Includes:
- public and plan-eligible suites
- active versions
- difficulty
- estimated cost envelope
- leaderboard eligibility

### `GET /v1/benchmark-suites/{suiteId}`
Detailed suite view.

### `GET /v1/benchmark-suites/{suiteId}/versions`
List suite versions.

### `GET /v1/benchmark-suites/{suiteId}/versions/{versionId}`
Version detail.

### `GET /v1/benchmark-suites/{suiteId}/practice-cases`
Return public/sample practice case previews only.

Query params:
- `difficulty`
- `count`

## 7. Compaction method endpoints

## 7.1 Method CRUD
### `GET /v1/projects/{projectId}/methods`
List methods for a project.

### `POST /v1/projects/{projectId}/methods`
Create method.

Request:
- `name`
- `methodType` (`built_in` or `external_callback`)
- `versionLabel`
- `description`
- `config`
- `builtInKey` or `endpointUrl`
- `timeoutMs`

### `GET /v1/projects/{projectId}/methods/{methodId}`
Method detail.

### `PATCH /v1/projects/{projectId}/methods/{methodId}`
Update method name, config, version label, endpoint, timeout, publication preference.

### `DELETE /v1/projects/{projectId}/methods/{methodId}`
Archive method.

## 7.2 Method secrets and verification
### `POST /v1/projects/{projectId}/methods/{methodId}/secrets`
Create or rotate callback auth secret.

### `DELETE /v1/projects/{projectId}/methods/{methodId}/secrets/{secretId}`
Revoke secret.

### `POST /v1/projects/{projectId}/methods/{methodId}/verify`
Run endpoint verification.

Optional request:
- `verificationType` (`ping`, `dry_run`, `schema_check`)

### `GET /v1/projects/{projectId}/methods/{methodId}/verifications`
List verification history.

## 7.3 Built-in method catalog
### `GET /v1/built-in-methods`
List platform built-ins.

### `GET /v1/built-in-methods/{builtInKey}`
Built-in method detail:
- description
- version
- config schema
- leaderboard eligibility

## 8. Experiment run endpoints

## 8.1 Run creation and listing
### `GET /v1/projects/{projectId}/runs`
List runs for a project.

Query params:
- `status`
- `suiteId`
- `methodId`
- `leaderboardStatus`
- `page`
- `pageSize`

### `POST /v1/projects/{projectId}/runs`
Create a run.

Request:
- `benchmarkSuiteVersionId`
- `seedSetId optional`
- `compactionMethodId`
- `targetModelKey`
- `executionMode`
- `driftCycleCount`
- `leaderboardSubmissionRequested`

Response:
- `runId`
- `status`
- `queuedAt`

### `GET /v1/projects/{projectId}/runs/{runId}`
Run summary.

Includes:
- versions
- status
- overall metrics when available
- leaderboard status

### `POST /v1/projects/{projectId}/runs/{runId}/cancel`
Cancel queued/running run if policy allows.

## 8.2 Run artifacts and diagnostics
### `GET /v1/projects/{projectId}/runs/{runId}/cases`
List case rows with aggregate status.

### `GET /v1/projects/{projectId}/runs/{runId}/cases/{caseId}`
Case detail.

### `GET /v1/projects/{projectId}/runs/{runId}/cases/{caseId}/cycles`
List cycles.

### `GET /v1/projects/{projectId}/runs/{runId}/cases/{caseId}/cycles/{cycleId}`
Cycle detail:
- compacted artifact summary
- scorecard
- invocation summary
- not hidden benchmark internals beyond what the user is allowed to inspect

### `GET /v1/projects/{projectId}/runs/{runId}/scorecard`
Run-level scorecard.

### `GET /v1/projects/{projectId}/runs/{runId}/comparison?againstRunId={id}`
Compare two runs.

## 8.3 Exports
### `POST /v1/projects/{projectId}/runs/{runId}/exports`
Generate export.

Request:
- `exportType` (`pdf`, `csv`, `json`)

### `GET /v1/projects/{projectId}/runs/{runId}/exports`
List exports.

### `GET /v1/projects/{projectId}/runs/{runId}/exports/{exportId}`
Download or retrieve signed URL.

## 9. Leaderboard submission endpoints

### `POST /v1/projects/{projectId}/runs/{runId}/submit-to-leaderboard`
Queue leaderboard qualification/publication for a completed eligible run.

### `GET /v1/projects/{projectId}/runs/{runId}/leaderboard-status`
Returns:
- requested
- eligible
- published
- rejected
- rejection reason

### `PATCH /v1/projects/{projectId}/runs/{runId}/leaderboard-publication`
Update published display options.

Request:
- `publishedMethodName`
- `publishedTeamName`
- `visibilityConsent`

## 10. Billing and usage endpoints

### `GET /v1/teams/{teamId}/billing`
Billing summary.

### `POST /v1/teams/{teamId}/billing/checkout-session`
Create Stripe checkout session.

### `POST /v1/teams/{teamId}/billing/portal-session`
Open customer portal.

### `GET /v1/teams/{teamId}/usage`
Usage summary for quota metering.

Query params:
- `from`
- `to`

## 11. Admin endpoints

Restrict to internal admins only.

## 11.1 Benchmark admin
### `POST /v1/admin/benchmark-suites`
Create suite.

### `PATCH /v1/admin/benchmark-suites/{suiteId}`
Update suite metadata.

### `POST /v1/admin/benchmark-suites/{suiteId}/versions`
Create suite version.

### `POST /v1/admin/templates`
Create template.

### `POST /v1/admin/templates/{templateId}/versions`
Create template version.

### `POST /v1/admin/suite-versions/{suiteVersionId}/assignments`
Assign template versions to suite version.

### `POST /v1/admin/suite-versions/{suiteVersionId}/publish`
Publish suite version.

## 11.2 Leaderboard admin
### `GET /v1/admin/leaderboards/{versionId}/entries`
List entries including hidden moderation metadata.

### `POST /v1/admin/leaderboards/{versionId}/recompute`
Recompute ranks.

### `POST /v1/admin/leaderboard-entries/{entryId}/suppress`
Suppress entry.

### `POST /v1/admin/leaderboard-entries/{entryId}/publish`
Manually publish approved entry.

## 11.3 Run admin
### `GET /v1/admin/runs/{runId}`
Deep run diagnostics.

### `POST /v1/admin/runs/{runId}/replay`
Replay failed run or subset of cases.

### `POST /v1/admin/runs/{runId}/recompute-scores`
Recompute scoring under same scorer version or migrate to a new scorer version explicitly.

## 12. Internal worker/orchestrator endpoints

If workers communicate over queue only, these may remain internal modules rather than public HTTP endpoints. If HTTP is used internally, keep them private.

Examples:
- `POST /internal/orchestrator/runs/{runId}/start`
- `POST /internal/run-cases/{caseId}/generate`
- `POST /internal/run-case-cycles/{cycleId}/execute`
- `POST /internal/run-case-cycles/{cycleId}/score`
- `POST /internal/runs/{runId}/aggregate`

## 13. External callback contract endpoint shape

This is not part of the public platform API but must be documented as a product contract.

### Platform -> user callback request
Payload should include:
- `invocationId`
- `schemaVersion`
- `transcript`
- `methodConfig`
- `constraints`
- `maxResponseBytes`
- `timeoutMs`

### Expected callback response
- `summaryText`
- `structuredState`
- `selectedSourceTurnIds`
- `warnings`
- `methodMetadata`

If schema validation fails, the platform rejects the cycle.

## 14. API response requirements

For all run/result responses, include:
- benchmark suite version
- scorer version
- method version
- model key/version where known

Without that, results are not auditable.

## 15. Final API verdict

Keep the API narrow and explicit. The important line is:

- API controls configuration and retrieval
- worker executes long-running tasks
- hidden benchmark content never leaks through convenience endpoints
