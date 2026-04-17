# CompactBench — Workorders (OSS v1)

Implementation plan from post-scaffold to public PyPI launch. Each workorder has objective, scope, deliverables, dependencies, and acceptance criteria.

Formulas, schemas, and policy numbers referenced below are locked in [decisions.md](decisions.md).

## Phase summary

| Phase | Workorders | Outcome |
|---|---|---|
| 0 — Scaffold | WO-001 | Package installs, tests pass |
| 1 — Core engine | WO-002, WO-003, WO-004 | Generate and score cases deterministically |
| 2 — Methods & providers | WO-005, WO-006 | Four built-ins run against real + mock models |
| 3 — Runtime | WO-007 | Full run end-to-end via CLI with drift cycles |
| 4 — Leaderboard & launch | WO-008, WO-009, WO-010 | Public leaderboard, hidden-set runner, PyPI release |

---

## WO-001 — Python package scaffold ✅

### Objective
Installable Python package with CLI entry point, typed contracts, CI pipeline, docs skeleton.

### Status
**Complete.**

### Deliverables
- `pyproject.toml` (uv-managed, hatchling build)
- `src/compactbench/` with `cli.py`, `contracts/`, package ABCs
- `tests/unit/` with smoke + contracts tests
- `.github/workflows/ci.yml`, issue + PR templates, CODEOWNERS
- MkDocs site skeleton, Apache 2.0 license, Contributor Covenant
- `CONTRIBUTING.md`, `CHANGELOG.md`

### Acceptance criteria
- `uv sync --all-extras --dev` succeeds
- `uv run pytest -m unit` passes
- `uv run ruff check .` passes
- `uv run pyright` passes

---

## WO-002 — Template DSL parser, generators, and schema validation

### Objective
Turn a YAML template file into a validated, deterministic template object ready for case generation.

### Scope
- JSON Schema for template files (`benchmarks/schemas/template-v1.json`)
- Parser in `src/compactbench/dsl/parser.py` — YAML → `TemplateDefinition` pydantic model
- Seeded generator registry in `src/compactbench/dsl/generators.py`: `person_name`, `action_phrase`, `project_noun`, `date_iso`, `amount_usd`, `product_sku`, `org_name`
- Validator in `src/compactbench/dsl/validator.py` — schema + semantic checks (variable references match declarations, difficulty policy well-formed)
- Handlebars-style `{{variable}}` substitution

### Dependencies
WO-001.

### Deliverables
- Three sample templates in `benchmarks/public/starter/`
- Round-trip tests: parse → validate → serialize
- Property tests (hypothesis) for generator determinism
- `compactbench suites list` wires up

### Acceptance criteria
- Same seed always produces same resolved template
- Invalid templates fail validation with actionable errors
- All seeded generators return deterministic output for a given seed

---

## WO-003 — Deterministic case generation engine

### Objective
Produce a concrete `GeneratedCase` from `(template, seed, difficulty)` with byte-identical output across runs.

### Scope
- `src/compactbench/engine/seeds.py` — seed derivation from `(suite_version, seed_group, case_slot)` using SHA-256 → PRNG
- `src/compactbench/engine/difficulty.py` — apply difficulty policy (distractor count, paraphrase depth, override timing)
- `src/compactbench/engine/transcript.py` — assemble the turn sequence
- `src/compactbench/engine/generation.py` — orchestrate: template + seed + difficulty → transcript + ground truth + evaluation items

### Dependencies
WO-002.

### Deliverables
- `compactbench generate --template <key> --seed <int>` works end-to-end
- Determinism regression test fixture (serialized expected output checked into `tests/fixtures/`)
- Per-difficulty golden-output tests

### Acceptance criteria
- Identical seeds produce byte-identical cases across Python minor versions and platforms
- Difficulty knobs measurably change output (more distractors at hard, later overrides at elite, etc.)
- Generation fully isolated from DB, HTTP, filesystem (pure function of inputs)

---

## WO-004 — Scoring engine

### Objective
Score a set of evaluation responses against the case's ground truth, producing per-cycle and per-case metrics.

### Scope
- `src/compactbench/scoring/checks.py` — check types: `contains_normalized`, `forbidden_absent`, `set_match`, `exact`, `numeric_within`, `entity_consistent`
- `src/compactbench/scoring/scorer.py` — weighted aggregation per [decisions.md §B3](decisions.md) B3 weights
- `src/compactbench/scoring/contradictions.py` — detect `locked_decision` / `forbidden_behavior` violations in responses
- `src/compactbench/scoring/drift.py` — drift delta + drift resistance across cycles
- `src/compactbench/scoring/compression.py` — cl100k-based compression ratio

### Dependencies
WO-002 (for contract access), WO-003 (for case fixtures in tests).

### Deliverables
- `compactbench score --results results.jsonl` prints run-level summary
- Scorer returns a pydantic `Scorecard` object matching `src/compactbench/contracts/result.py`
- Coverage >= 90% for scoring package

### Acceptance criteria
- Boundary cases: all-pass, all-fail, single-item runs, zero-denominator safeguards
- Compression ratio matches hand-computed value for a known transcript
- Drift resistance = 1.0 for a method that holds every cycle; < 1.0 for a degrading method

---

## WO-005 — Built-in compactors

### Objective
Ship four baseline compaction methods. All validate against the artifact schema.

### Scope
- `src/compactbench/compactors/naive_summary.py` — single summarization call, empty structured state
- `src/compactbench/compactors/structured_state.py` — JSON-schema-forced extraction, no `summaryText`
- `src/compactbench/compactors/hierarchical_summary.py` — chunk → summarize → meta-summarize
- `src/compactbench/compactors/hybrid_ledger.py` — append-only ledger across cycles via `previous_artifact`
- Registry in `src/compactbench/compactors/__init__.py` for `built-in:<key>` resolution

### Dependencies
WO-003, WO-006 (needs provider to call a model).

### Deliverables
- Each compactor runnable via `compactbench run --method built-in:<key>`
- Integration tests using the mock provider for deterministic output
- Each method has a README section documenting its prompt template and config schema

### Acceptance criteria
- All four return valid `CompactionArtifact` on every call
- None skip any `structuredState` section (empty arrays permitted, missing keys not)
- Hybrid-ledger accumulates across cycles (verified with 2-cycle integration test)

---

## WO-006 — Provider clients

### Objective
Model provider abstractions with concrete implementations for Groq, Google AI Studio, Ollama, and a deterministic mock.

### Scope
- `src/compactbench/providers/base.py` — already scaffolded; review + extend
- `src/compactbench/providers/groq.py` — async client, 429 backoff, typed errors
- `src/compactbench/providers/google_ai_studio.py` — same
- `src/compactbench/providers/ollama.py` — local HTTP client
- `src/compactbench/providers/mock.py` — prompt-hash → canned response map, deterministic
- `src/compactbench/providers/registry.py` — `--provider <key>` resolves to the right client

### Dependencies
WO-001.

### Deliverables
- `compactbench providers list` shows all registered providers
- Per-provider integration test (skipped in CI when no key is configured)
- Contract test: all providers return identical response shape for identical request

### Acceptance criteria
- Mock provider is fully offline and deterministic
- Real providers respect env-var config from `COMPACTBENCH_*` namespace
- 429s from Groq/Google produce backoff retries, not hard failures

---

## WO-007 — Runner, CLI orchestration, drift cycles

### Objective
End-to-end: `compactbench run` generates cases, calls the compactor, invokes the model, scores results, writes `results.jsonl`, supports drift cycles.

### Scope
- `src/compactbench/runner/run.py` — orchestrate a full run
- `src/compactbench/runner/cycle.py` — drift cycle execution with continuation prompts
- `src/compactbench/runner/persistence.py` — JSONL writer, resume support
- Wire up `compactbench run` and `compactbench score` command bodies

### Dependencies
WO-004, WO-005, WO-006.

### Deliverables
- Full run on `starter` suite using mock provider completes in < 30 seconds
- Full run on `elite_practice` with Groq completes and produces a valid `RunResult`
- `--resume` flag picks up from last completed case

### Acceptance criteria
- `results.jsonl` matches the `RunResult` schema from `src/compactbench/contracts/result.py`
- Drift cycles execute in order; later cycles can access `previous_artifact`
- Interrupted runs resume cleanly without double-counting completed cases

---

## WO-008 — GitHub Actions submission flow + leaderboard site

### Objective
PR-based submission pipeline that evaluates methods against the hidden set on the self-hosted runner and publishes the public leaderboard.

### Scope
- `.github/workflows/evaluate-submission.yml` — triggers on `evaluate` label; runs on `self-hosted` runner; clones hidden repo; executes method against Elite Ranked; comments score back to PR
- `.github/workflows/update-leaderboard.yml` — runs on merge of a qualified submission; updates `site/data/leaderboard.json`; rebuilds static site; deploys to GitHub Pages
- `site/` — static leaderboard site (Astro or MkDocs plugin); deployed to `compactbench.dev`
- `src/compactbench/leaderboard/{ranking,qualification,projection}.py` — ranking formula + floors + JSON projection
- Submission scaffolding in `submissions/_template/`

### Dependencies
WO-007.

### Deliverables
- End-to-end: a dummy PR with `submissions/test/sample-method/` triggers evaluation on the runner and posts scores to the PR
- Leaderboard site live at `compactbench.dev/leaderboard`
- `compactbench submit` command drafts a PR-ready submission directory from a local `results.jsonl`

### Acceptance criteria
- Hidden test content never appears in public workflow logs
- Provider keys never leak into PR-author-runnable workflows
- Leaderboard updates deterministically on merge
- Leaderboard segmented by benchmark version + target model

---

## WO-009 — Launch Elite templates (3 families)

### Objective
Ship the three launch families as public practice + hidden ranked content.

### Scope
- Public practice templates in `benchmarks/public/elite_practice/`:
  - `buried_constraint_v1.yaml` (5 variations)
  - `decision_override_v1.yaml` (5 variations)
  - `entity_confusion_v1.yaml` (5 variations)
- Hidden ranked templates in the private `compactbench-hidden` repo:
  - 20 seed variations per family (60 total)
- Governance doc at `docs/governance/elite-versions.md` — v1 Elite changelog
- Seed group policy: each leaderboard version draws a fixed seed group per template

### Dependencies
WO-002, WO-003, WO-008.

### Deliverables
- Public practice runs of all three families succeed end-to-end with hybrid-ledger baseline
- Hidden ranked runs on the self-hosted runner produce valid scorecards
- Governance doc explains version policy, retirement policy, seed rotation

### Acceptance criteria
- All three families cover their documented failure mode (buried constraint / decision override / entity confusion)
- Hidden content is never referenced in public repo commit history
- Determinism regression tests for all 15 public seeds

---

## WO-010 — Docs site, PyPI release, launch announcement

### Objective
First public `0.1.0` release on PyPI, docs site live, launch communications prepared.

### Scope
- Polish all MkDocs pages: `getting-started`, `writing-a-compactor`, `submitting`, `methodology`, `elite-program`
- Add a "Try it in 3 minutes" quickstart with Ollama
- `.github/workflows/release.yml` — tag push → build wheels → PyPI publish (trusted publishing via OIDC)
- Populate `CHANGELOG.md` for `0.1.0`
- Launch post draft (HN Show, r/LocalLLaMA, AI Twitter)
- Verify domain resolves, Pages deploys, PyPI install works

### Dependencies
All prior workorders.

### Deliverables
- `pip install compactbench` works against PyPI
- `compactbench.dev` serves docs + leaderboard
- Launch post reviewed and ready to ship

### Acceptance criteria
- A cold user can go from `pip install compactbench` to seeing their first run in under 3 minutes (with Ollama pre-installed)
- Every public doc page renders and links resolve
- PyPI package metadata is correct (keywords, classifiers, project URLs)
- First leaderboard version is frozen and documented

---

## Post-v1 roadmap (out of scope here)

- Elite families 4–15 (monthly release cadence)
- Automated shadow evaluation scheduling
- Anthropic / OpenAI / Google Vertex provider integrations
- Research paper + arXiv submission
- Sponsorship acceptance
- Third-party Dockerized runner distribution
