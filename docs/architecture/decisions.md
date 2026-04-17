# CompactBench — Technical Decisions (v1, locked)

## Status

- **Version**: 1.0 (OSS)
- **Date locked**: 2026-04-16
- **Scope**: canonical reference for all workorders through v1 PyPI release.
- **Supersedes**: the SaaS-era decisions document (archived at [_legacy-saas/decisions.md](_legacy-saas/decisions.md)).

CompactBench is an open-source Python package distributed on PyPI. The leaderboard is operated by maintainers; submissions arrive as PRs and are evaluated by a GitHub Actions self-hosted runner that holds the hidden test set and provider API keys.

---

## Part A — Language, tooling, and distribution

### A1. Language
Python 3.12 target; minimum supported 3.11; tested on 3.11 / 3.12 / 3.13 in CI.

### A2. Package manager
[uv](https://github.com/astral-sh/uv) (Astral). `uv sync` is the one command contributors run after clone.

### A3. Build backend
Hatchling. Declared in `pyproject.toml`; produces wheels and sdists.

### A4. Linting + formatting
Ruff. One tool for both. Config in `pyproject.toml`.

### A5. Type checking
Pyright in strict mode. `py.typed` marker ships with the package.

### A6. Testing
pytest + pytest-asyncio + pytest-cov + hypothesis (for property-based determinism tests).

### A7. CLI framework
Typer + Rich. Entry point: `compactbench`.

### A8. Schema validation
pydantic v2 for runtime models; JSON Schema (draft 2020-12) for templates and artifacts; jsonschema library for external artifact validation.

### A9. YAML
ruamel.yaml (round-trip support for template authoring).

### A10. HTTP
httpx (sync + async; used by all provider clients).

### A11. Tokenizer
tiktoken, `cl100k_base` encoding. Applied to every method × model pair so compression ratios are comparable.

### A12. Docs site
MkDocs Material, served from GitHub Pages on the `compactbench.dev` apex domain.

### A13. Leaderboard site
Static site on the same GitHub Pages deployment, generated from `site/data/leaderboard.json` by a GH Actions workflow on merge of a qualified submission.

### A14. License
Apache License 2.0. Patent grant matters when third parties submit methods.

### A15. Pre-commit
Enabled by default. ruff (check + format) + pyright + basic hygiene hooks.

---

## Part B — Product content (carried forward from SaaS decisions)

The mathematical and structural decisions that defined the product are unchanged. Where a workorder needs an exact formula, it lives here.

### B1. Benchmark template DSL
YAML templates with Handlebars-style `{{variable}}` substitution, JSON Schema validation of the template file itself, and deterministic seeded generators.

Seeded generators: `person_name`, `action_phrase`, `project_noun`, `date_iso`, `amount_usd`, `product_sku`, `org_name`. Each draws from a bounded lexicon and advances a seeded PRNG.

See canonical example in [_legacy-saas/decisions.md §B1](_legacy-saas/decisions.md).

### B2. Compaction artifact schema
Strict JSON Schema. Every section required; empty arrays / empty object allowed; missing keys rejected. Implemented as pydantic models in `src/compactbench/contracts/artifact.py`.

Full schema in [_legacy-saas/decisions.md §B2](_legacy-saas/decisions.md). Schema version: `1.0.0`.

### B3. Scoring formulas

**Item weights** (by `item_type`):

| item_type | weight |
|---|---|
| `locked_decision_retention` | 3 |
| `forbidden_behavior_retention` | 3 |
| `immutable_fact_recall` | 2 |
| `unresolved_task_continuity` | 2 |
| `entity_integrity` | 1 |
| `planning_soundness` | 1 |

**Cycle score**: `cycle_score = sum(weight_i * item_score_i) / sum(weight_i)`

**Contradiction rate**: `violating_responses / total_responses`

**Penalized cycle score**: `cycle_score * (1 - contradiction_rate)`

**Drift resistance**: `clamp(1 + mean(cycle_score_n - cycle_score_0 for n >= 1), 0, 1)`

**Compression ratio**: `tokens(transcript) / (tokens(summary_text) + tokens(structured_state))` using cl100k_base.

### B4. Leaderboard ranking

```
elite_score =
    0.40 * run_overall_score
  + 0.30 * drift_resistance
  + 0.20 * constraint_retention
  + 0.10 * compression_bonus
```

Tie-breakers: higher drift_resistance → higher constraint_retention → lower contradiction_rate → earlier `published_at`.

**Qualification floors** (all must pass):
- `compression_ratio >= tier_floor` (B9)
- `contradiction_rate <= 0.10`
- all configured case slots completed
- all configured drift cycles completed (v1 default: 2)
- no single family below 0.40 case-level pass rate
- no runner failures in ranked slots

### B5. Built-in compactors
`naive-summary`, `structured-state`, `hierarchical-summary`, `hybrid-ledger`. Algorithm sketches in [_legacy-saas/decisions.md §B5](_legacy-saas/decisions.md).

### B6. Launch Elite families
`buried_constraint_v1`, `decision_override_v1`, `entity_confusion_v1`. Each: 5 public practice variations + 20 hidden ranked variations. Remaining 12 families added post-launch.

### B7. Compression tier floors
- Elite-Light: ≥ 2.0×
- Elite-Mid: ≥ 4.0×
- Elite-Aggressive: ≥ 8.0×

### B8. Starter/Hard suites
Starter public (20 cases, no compression floor), Hard public (30 cases, no compression floor). Used for development and practice, not ranked.

---

## Part C — Distribution

### C1. PyPI
- Package name: `compactbench`
- Release cadence: SemVer, first release `0.1.0` after WO-007
- Trusted publishing via GitHub Actions OIDC (no long-lived PyPI token)

### C2. GitHub
- Public repo: `compactbench/compactbench`
- Private hidden-set repo: `compactbench/compactbench-hidden`
- Docs + leaderboard: GitHub Pages on `compactbench.dev`

### C3. Domain
`compactbench.dev` registered via a standard registrar (Porkbun or Namecheap — post-scaffold decision). Cloudflare (free plan) for DNS + CDN.

### C4. Branding
Short name "CompactBench". Tagline: *"Open benchmark for AI conversation compaction methods."*

---

## Part D — Model providers

### D1. Primary
Groq free tier: `llama-3.3-70b-versatile`, `kimi-k2-instruct`.

### D2. Secondary
Google AI Studio free tier: `gemini-2.0-flash`.

### D3. Local dev
Ollama: `llama3.2` and similar. No API key required.

### D4. Testing
Mock provider in `src/compactbench/providers/mock.py`. Deterministic responses keyed by prompt hash.

### D5. User responsibility
Users supply their own API keys via environment variables (`COMPACTBENCH_GROQ_API_KEY`, etc.). The package makes no upstream calls without a configured key.

### D6. Leaderboard evaluation
The maintainer-operated runner uses the same providers via repository secrets. First leaderboard version pins **Groq + Llama 3.3 70B**; second pins **Gemini 2.0 Flash**.

### D7. Deferred
Anthropic Claude, OpenAI GPT, Google Vertex AI — integration when a funding path opens.

---

## Part E — Leaderboard runner infrastructure

### E1. Runner
GitHub-hosted `ubuntu-latest` runners (free and unlimited for public repos).

No self-hosted VM for v1. Earlier drafts planned an Oracle Cloud self-hosted runner for outbound-firewall control; we dropped it because (a) it's zero cost only on Oracle's increasingly unreliable free tier, (b) the operational burden outweighs the isolation benefit for a pre-scale project, and (c) the same security properties come from the `pull_request_target` + manual-label flow described in E3–E5 below.

We can migrate to self-hosted later without changing the workflow shape if there is a specific incident or a scale need.

### E2. Evaluation workflow
`.github/workflows/evaluate-submission.yml` triggers on `pull_request_target` with the `evaluate` label. It runs on GitHub-hosted `ubuntu-latest` and:

1. Checks out the PR's head commit (contains the submission's method source).
2. Clones `compactbench/compactbench-hidden` using a deploy key stored as a repo secret.
3. Installs `compactbench` plus the submission's declared deps.
4. Runs `compactbench run` against the hidden Elite Ranked suite.
5. Posts the score summary as a PR comment and uploads the results file as a workflow artifact.

### E3. Secret exposure model
`pull_request_target` runs in the trusted context of the target repo (not the PR author's fork) with access to repo secrets. The workflow is only authorized to run once a **maintainer applies the `evaluate` label** after reviewing the submission's code. This review is the security gate.

Provider API keys (`GROQ_API_KEY`, `GOOGLE_AI_STUDIO_API_KEY`) and the hidden-repo deploy key are stored as repo secrets scoped to the `evaluate-submission.yml` workflow environment. They are not accessible to regular `pull_request` events or to other workflows.

### E4. Evaluation gating
Maintainers must manually apply the `evaluate` label to each submission PR after code review. The label's existence is what authorizes the workflow to run with secrets. No auto-labeling, no drive-by evaluations.

### E5. Leaderboard publication
On merge of a qualified submission, `update-leaderboard.yml` rebuilds `docs/data/leaderboard.json` from all committed submissions and triggers the existing docs deploy. Served from the same GitHub Pages deployment as the docs.

### E6. Cost
$0. GitHub Actions free minutes (unlimited for public repos) + GitHub Pages free hosting. Optional later: domain registration (~$12/year).

### E7. Migration path
If we ever need self-hosted (e.g., for outbound-firewall allow-listing or for compliance), add a single `runs-on: [self-hosted, evaluate]` override to the evaluate workflow and register the runner. No changes to the submission flow, leaderboard core, or secret model.

---

## Part F — Governance

### F1. Maintainers
Initial maintainer: project owner. Additional maintainers added via invite to the `compactbench/maintainers` GitHub team. Hidden-repo access is granted separately and revocably.

### F2. Elite version review
Quarterly. Retire compromised template families, add new ones, document in `CHANGELOG.md` and a dedicated `docs/governance/elite-versions.md`.

### F3. Leaderboard versioning
Each leaderboard version is segmented by `(benchmark_version, target_model)`. Historical leaderboards stay pinned to their original versions forever.

### F4. Template retirement
Public retirement notice in the changelog; hidden template is removed from the ranked pool but not deleted (preserved in the hidden repo for audit).

### F5. Suspicion review
Flagged submissions (low public variance + hidden collapse, narrow family concentration, brittle shadow results) are reviewed by a maintainer before publication. Process documented publicly; heuristics documented privately.

### F6. Code of conduct
Contributor Covenant 2.1. Reports to `conduct@compactbench.dev` (routed to maintainers).

---

## Part G — Deferred to post-launch

- Paid model providers (Anthropic / OpenAI / Google Vertex / Mistral)
- Automated shadow evaluation scheduling
- Elite template families 4–15 (content roadmap)
- Sponsorship acceptance process
- Non-English benchmark content
- Python 3.10 backport
- Dockerized runner distribution for third-party evaluators
- Research paper + arXiv submission

---

## Part H — Budget

| Cost | Amount |
|---|---|
| Hosting, CI, docs, leaderboard, runner | $0 |
| PyPI publishing | $0 |
| Domain registration (`compactbench.dev`) | ~$12/year |
| **v1 launch total** | **~$12/year** |

No other paid dependencies. Every item in Parts A–F runs on a forever-free tier or is self-hosted on the Oracle free VM.

---

## Revision history

| Version | Date | Change |
|---|---|---|
| 1.0 | 2026-04-16 | Initial OSS lock, superseding SaaS decisions v1.0 |
