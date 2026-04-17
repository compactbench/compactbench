# 05. Page Map

## 1. Page strategy

The page map should reflect the actual product model:

- public trust surfaces first
- authenticated build-and-run surfaces second
- admin surfaces isolated
- benchmark engine hidden behind clear workflows

Do not build a generic "chat" surface. This is an experiment product.

## 2. Public routes

## 2.1 `/`
Purpose:
- product homepage
- value proposition
- CTA to sign up
- headline benchmark credibility
- public leaderboard teaser

Key blocks:
- hero
- product explanation
- benchmark categories
- why leaderboard is hard to game
- CTA

## 2.2 `/leaderboard`
Purpose:
- public leaderboard list

Shows:
- active leaderboard version selector
- overall rankings
- filters: model, difficulty, compression tier
- method name / org name / score breakdown

No login required.

## 2.3 `/leaderboard/[versionKey]/[entryId]`
Purpose:
- public detail page for one published method run

Shows:
- score breakdown
- elite score
- drift chart
- comparison to platform baselines
- benchmark version and model
- sanitized failure category examples

## 2.4 `/methodology`
Purpose:
- explain scoring and benchmark philosophy

Shows:
- what is measured
- why seeded randomness exists
- why hidden ranked sets exist
- what leaderboard scores mean
- benchmark versioning policy

## 2.5 `/benchmarks`
Purpose:
- public benchmark catalog

Shows:
- starter, hard, elite
- public descriptions
- practice mode explanation
- no hidden full cases

## 2.6 `/benchmarks/[suiteKey]`
Purpose:
- public suite detail page

Shows:
- suite purpose
- difficulty
- category mix
- sample practice cases
- leaderboard eligibility

## 2.7 `/pricing`
Purpose:
- plan explanation

## 2.8 `/login`
Purpose:
- auth entry

## 2.9 `/signup`
Purpose:
- registration

## 3. Authenticated routes

## 3.1 `/app`
Purpose:
- authenticated landing / dashboard redirect

Recommended behavior:
- redirect to last active project or project list

## 3.2 `/app/projects`
Purpose:
- project list

Shows:
- projects by team
- recent run counts
- latest run status
- create project CTA

## 3.3 `/app/projects/new`
Purpose:
- create project

Fields:
- team
- project name
- description

## 3.4 `/app/projects/[projectId]`
Purpose:
- project dashboard

Shows:
- recent runs
- methods
- benchmark quick actions
- quota summary
- leaderboard publications

This is the operational home page for a project.

## 3.5 `/app/projects/[projectId]/methods`
Purpose:
- method list

Shows:
- built-in methods used by this project
- external callback methods
- status/verification state
- leaderboard publications by method

## 3.6 `/app/projects/[projectId]/methods/new`
Purpose:
- create method

Tabs:
- built-in
- external callback

Built-in flow:
- select built-in key
- configure parameters
- name/version label

External flow:
- endpoint URL
- timeout
- auth setup
- config JSON or structured fields
- verification CTA

## 3.7 `/app/projects/[projectId]/methods/[methodId]`
Purpose:
- method detail

Shows:
- config
- verification history
- usage history
- last run summary
- publication status

## 3.8 `/app/projects/[projectId]/runs`
Purpose:
- run list

Shows:
- filters
- status
- suite
- method
- model
- leaderboard status
- created time

## 3.9 `/app/projects/[projectId]/runs/new`
Purpose:
- create run

This is a critical page.

Sections:
1. benchmark suite selection
2. difficulty / suite version
3. method selection
4. model selection
5. execution mode
6. drift cycles
7. leaderboard submission toggle
8. estimated cost/time summary

## 3.10 `/app/projects/[projectId]/runs/[runId]`
Purpose:
- run summary page

Shows:
- overall metrics
- run status
- benchmark/method/model/scorer versions
- leaderboard eligibility
- aggregate charts
- export actions
- compare-to-run action

## 3.11 `/app/projects/[projectId]/runs/[runId]/cases`
Purpose:
- case grid/list

Shows:
- per-case status
- aggregate score
- failure categories
- template family
- cycle counts

## 3.12 `/app/projects/[projectId]/runs/[runId]/cases/[caseId]`
Purpose:
- case inspector

Shows:
- generated transcript summary
- compacted artifact summary
- cycle navigator
- evaluation items
- score breakdown
- invocation failures
- warnings

Do not expose hidden ranked case internals beyond the allowed user inspection policy.

## 3.13 `/app/projects/[projectId]/runs/[runId]/compare/[otherRunId]`
Purpose:
- run comparison page

Shows:
- side-by-side overall metrics
- delta by category
- delta by drift
- top gains and regressions
- cases with biggest change

## 3.14 `/app/projects/[projectId]/exports`
Purpose:
- export history

## 3.15 `/app/teams/[teamId]/settings`
Purpose:
- team settings
- billing
- invite members
- usage

## 3.16 `/app/profile`
Purpose:
- user profile
- default team
- API/auth info if relevant

## 4. Admin routes

Restrict to internal admins.

## 4.1 `/admin`
Admin landing/dashboard.

## 4.2 `/admin/benchmarks`
Suite list.

## 4.3 `/admin/benchmarks/suites/[suiteId]`
Suite detail.

## 4.4 `/admin/templates`
Template list.

## 4.5 `/admin/templates/[templateId]`
Template/version detail.

## 4.6 `/admin/leaderboards`
Leaderboard version list.

## 4.7 `/admin/leaderboards/[versionId]`
Leaderboard admin detail.

## 4.8 `/admin/runs/[runId]`
Deep run diagnostics.

## 4.9 `/admin/providers`
Provider/model config.

## 5. Primary user flows

## 5.1 New user -> first run
1. sign up
2. create team
3. create project
4. choose built-in method
5. choose starter benchmark
6. launch run
7. inspect results
8. upgrade or add callback method later

## 5.2 Advanced user -> custom callback
1. create project
2. add external callback method
3. configure auth secret
4. run verification
5. choose hard or elite suite
6. launch run
7. review failures
8. resubmit improved version

## 5.3 Public discovery -> leaderboard conversion
1. browse leaderboard
2. click top method detail page
3. read methodology
4. sign up
5. create project and run benchmark

## 6. Page map rules

- keep hidden benchmark details off public pages
- keep business logic in API/backend
- never let frontend decide benchmark eligibility, quota eligibility, or leaderboard eligibility
- present benchmark versions and scorer versions on result pages
- give users enough failure detail to improve, but not enough hidden detail to memorize ranked tests

## 7. Final page-map verdict

The most important authenticated pages are:

- project dashboard
- method creation/detail
- run creation
- run summary
- case inspector
- run comparison

The most important public pages are:

- leaderboard
- method detail
- methodology
- benchmark catalog

Those are the pages that drive trust, product value, and growth.
