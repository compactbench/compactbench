# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] — 2026-08-24

### Scoring integrity — **scorer_version 1.0.0 → 2.0.0**

Scores produced by scorer 1.0.0 are **not comparable** to these. The leaderboard
segments on `scorer_version`, so old and new rows never mix. Four defects meant a
method that did nothing intelligent would have topped the first leaderboard.

- **Compaction methods no longer receive the answer key.** Generated turns carry
  `tags` — `distractor` on filler, `critical_constraint` on the turn holding the
  answer — and the runner handed them straight to the method. A five-line
  compactor with no model call that keeps the non-`distractor` turns recovered
  100% of the recall items at ~9x compression. Tags are now stripped at the
  compaction boundary (this also closes the same leak through the LangChain and
  LlamaIndex adapters); they remain on the case for diagnostics.
- **`drift_resistance` no longer rewards consistent failure.** It was
  `clamp(1 + mean(score[n] - score[0]))` — a measure of whether scores *change*,
  not whether they are any good — so a method scoring 0.0 on every cycle was
  perfectly stable and scored **1.0**, collecting 30% of `elite_score` for the
  worst possible result. It is now a retention ratio,
  `mean(later) / first`, and is 0.0 when unmeasurable (fewer than two cycles, or
  a zero baseline) rather than a free 1.0. Empty and crashed runs aggregate to
  0.0 drift resistance instead of 1.0.
- **The JSON state parser recovers objects wrapped in prose.** It required the
  response to be bare JSON or a fenced block, so `Here is the state: {...}`, a
  trailing `Hope that helps!`, and `<think>` preambles all produced a fully
  empty state that scored as total information loss — measuring the parser
  rather than the method, and worst on exactly the small and local models the
  benchmark should be free to run on. Brace matching is string- and
  escape-aware, so quoted code containing `}` no longer truncates the object.
- **Qualification closes four routes to an unearned rank.** Control arms are
  never ranked; compression above 50x is rejected as a degenerate/empty artifact
  (the `null` arm measures ~450x and previously cleared every tier and maxed the
  compression bonus); runs configured with zero drift cycles are unrankable,
  since drift is 30% of the score and they never measured it; and a run whose
  results file has no `run_end` event is rejected, so a crashed run cannot
  publish a partial score and stopping early is not a way to cherry-pick.

### Security — submission evaluation pipeline

- **The evaluation workflow could never succeed, and reported it as the submitter's fault.**
  It checked out the PR head at the default `fetch-depth: 1`, then ran
  `git diff <base> <head>`. The base commit does not exist in a shallow clone, so
  the diff failed, the failure was swallowed by `|| true`, and the job exited with
  "PR does not touch any submissions/<handle>/<method>/ directory". Every
  submission would have been turned away with a misleading error. Now `fetch-depth: 0`.
- **The hidden ranked set was exfiltrable with no code execution.** The config step
  interpolated five unvalidated submitter-controlled YAML values into a file and
  appended it to `$GITHUB_ENV`. A newline in `runtime.model` injected arbitrary
  job-wide environment variables; since `OllamaProvider` passes
  `COMPACTBENCH_OLLAMA_BASE_URL` straight to its client, a submission with
  `provider: ollama` would have caused the runner to POST **every hidden ranked
  case to an attacker-controlled host as a prompt**. No `method.py` runs on that
  path, so sandboxing submitter code would not have closed it. All values now go
  through `scripts/validate_submission_config.py` — allow-listed provider,
  whitespace-free model pattern, bounded integers, control characters rejected,
  and `class_path` required to sit inside the submission directory the PR
  actually touched. Values never transit `$GITHUB_ENV`; the runner reads them
  from validated JSON. 35 tests cover it, including the concrete attack payload.
- **Script injection in the score comment.** `body: \`${{ steps.summary.outputs.body }}\``
  placed submitter-influenced text (the method name reaches it via
  `compactbench score` output) inside a JS template literal, where a backtick or
  `${...}` escapes into arbitrary JavaScript in a step holding a write-scoped
  `GITHUB_TOKEN`. Passed via `process.env` instead.
- **The hidden-set token no longer persists on disk.** It was embedded in the
  clone URL, which git writes verbatim into `/tmp/hidden/.git/config` — leaving a
  credential that regenerates the entire hidden set readable by submitter code
  executing later in the same job. Now passed via `GIT_ASKPASS`, with the `.git`
  directory removed once the working tree exists.
- `scripts/validate_submissions.py` now validates every submission config, not
  just greps for leftover `FILL_ME` placeholders, so contributors get the error
  on their PR instead of after a maintainer applies the `evaluate` label.
- `ollama` and `mock` are no longer accepted as ranked-evaluation providers. Both
  can be pointed at an arbitrary host, and the evaluator must control where calls go.

### Added — control arms
- `oracle`, `null`, and `truncate-last-n` built-ins. None makes a model call, so
  they are free and deterministic to run alongside any experiment. A score in
  isolation is uninterpretable: the oracle bounds what is achievable when
  compaction loses nothing, and the null arm exposes how many points are
  available with no information at all. Measured against a real model, the
  oracle scores **0.650**, not 1.0 — so a method scoring 0.5 has not lost half
  the information, it is at 77% of the achievable ceiling.
- `compactbench qualify --results <file>` — runs the leaderboard floors locally
  and prints every reason a run would be rejected. Previously a submitter could
  only discover a disqualification by opening a PR and waiting for a maintainer,
  after having already spent the API budget on the run.
- `CompactionArtifact` accepts either Python field names or the camelCase wire
  aliases (`populate_by_name`). `summary_text=` previously raised
  "Extra inputs are not permitted" while `summaryText=` worked — a confusing
  first failure for anyone writing a method, which the docs' own example
  half-tripped over by mixing the two styles.

Four months of merged work that was never released, plus the packaging fix that
makes it reachable. **If you installed 0.1.0, upgrade** — that wheel shipped
without any benchmark content, so `compactbench suites list` failed on a clean
install and no benchmark could be run from PyPI at all.

### Fixed
- **The published wheel now contains the benchmark suites.** The `force-include`
  mapping that bundles `benchmarks/public` landed in #21, *after* the v0.1.0 tag,
  so the released artifact had zero templates and the documented first command
  exited 1. CI and the release workflow now install the built wheel into a clean
  environment and assert the CLI can see `starter` and `elite_practice`, so this
  class of packaging regression cannot ship again.
- `.env` is now actually read. Every provider reads `os.environ` directly, and
  the `Settings` object that parsed `.env` was imported by nothing — the
  documented way to supply API keys silently did nothing. The CLI now loads
  `COMPACTBENCH_*` variables from `.env` before any provider is constructed.
  A real environment variable still wins over the file.
- An empty `COMPACTBENCH_OPENAI_BASE_URL` no longer marks a genuine OpenAI run
  as self-hosted. The client was gated on truthiness and the provenance flag on
  identity, so `""` produced a run stamped as having gone somewhere it hadn't.
- A base URL without an `http://` or `https://` scheme is now rejected at
  construction instead of failing much later with an opaque connection error.
- `uv.lock` regenerated (90 → 145 packages; it had not been touched since the
  initial scaffold and was missing the `anthropic` and `openai` entries
  entirely). All workflows now install with `--locked`, so CI fails on lock
  drift rather than silently re-resolving against live PyPI on every run — which
  matters for a project whose central claim is reproducibility.
- The test suite no longer inherits the developer's environment: an autouse
  fixture clears `COMPACTBENCH_*`, fixing `test_requires_api_key` failing for
  anyone with a base URL exported (i.e. exactly the local-model users).

### Added
- **Endpoint provenance.** `run_start` and `RunResult` now carry `endpoint_kind`
  (`"default"` or `"custom"`), sourced from the provider, and it is part of the
  leaderboard's ranking segment. Without it a locally-served model submitted as
  `--provider openai --model gpt-4o` was ranked against genuine gpt-4o — the
  provider and model fields are both caller-supplied strings. `--resume` also
  checks it, so a run cannot be half-executed against a hosted model and
  finished against a local one under the same alias. The URL itself is never
  stored; results files get shared and the host is often internal.
- `OpenAIProvider` accepts a `base_url` (constructor argument or
  `COMPACTBENCH_OPENAI_BASE_URL`), so the `openai` provider also serves any
  OpenAI-compatible endpoint — vLLM, llama.cpp server, LM Studio, Together,
  Fireworks, OpenRouter (#37, thanks @jaaabir). When a base URL is set the API
  key becomes optional, because self-hosted servers generally do not check one.
- Anthropic and OpenAI providers (#19).
- LangChain (#16) and LlamaIndex (#17) integration adapters.
- Zero-install Colab notebook (#18) with a CI smoke test that rebuilds it from
  its generator and executes every embedded command against the mock provider.
- Case-level parallelism and a `--estimate` cost projector (#22).
- Prompt caching via `cached_prefix` on `CompletionRequest` (#23).
- `reference_resolution` template family (#27) — a fourth family, 5 templates —
  and a per-item-type diagnostic breakdown in `compactbench score`.
- Per-cycle / per-case / per-run `TokenUsage` telemetry (#28).

### Changed
- Cost catalogue refreshed and made self-policing: `--estimate` now prints the
  price vintage alongside the dollar figure, and a test fails once the catalogue
  is more than 120 days old. Anthropic entries updated to the current lineup;
  the previous table priced models that have since been superseded and had no
  entry for any current one, so `--estimate` either quoted stale rates or
  refused to answer.
- Pinned GitHub Action SHAs bumped (#34).
- Docs corrected to describe the project that actually exists: four template
  families and 20 practice templates (not three and 15), five real providers
  (not three), and `~900` calls for a full Elite practice run (not `~450`).

## [0.1.0] — 2026-04-17

First public release. The full v1 stack: DSL parser, case-generation engine,
scoring engine, mock + real providers, built-in compactors, end-to-end runner,
submission pipeline with public leaderboard, and 15 Elite practice templates
across three launch families.

### Added
- Initial project scaffold: Python package layout, CLI entrypoint, core ABCs
- Apache 2.0 license
- Contributor guide and code of conduct
- MkDocs documentation skeleton
- GitHub Actions CI workflow
- Template DSL (WO-002):
  - YAML + Handlebars-style `{{variable}}` substitution
  - Pydantic models for `TemplateDefinition` and sub-structures
  - Seeded generator registry: `person_name`, `action_phrase`, `project_noun`,
    `org_name`, `date_iso`, `amount_usd`, `product_sku`
  - SHA-256-based sub-seed derivation for reordering-stable determinism
  - Semantic validator for references, generators, and duplicate names
  - JSON Schema at `benchmarks/schemas/template-v1.json`
  - Three starter templates: `buried_constraint_starter_v1`,
    `decision_override_starter_v1`, `entity_confusion_starter_v1`
  - `compactbench suites list` command wired up
- Elite v1 public practice templates (WO-009):
  - 15 templates in `benchmarks/public/elite_practice/`, 5 variations each for
    the three launch families: `buried_constraint_v1`, `decision_override_v1`,
    `entity_confusion_v1`
  - Variations within each family probe different failure modes (e.g.,
    indirect phrasing, double constraints, negative examples, sandwich
    layouts for `buried_constraint`; simple/three-way/partial/late/meta-reset
    overrides for `decision_override`; 2-person/3-person/same-role/
    observer-vs-owner/shared-project for `entity_confusion`)
  - Difficulty policy scales distractor turns 4 → 8 → 16 → 32 from easy to
    elite, matching the ranked set's expected adversarial load
  - `compactbench suites list` now shows `elite_practice` with 15 templates
    across 3 families
  - `docs/governance/elite-versions.md` — active-version table, version
    policy, retirement policy, anti-gaming reminders, v1 changelog
  - 9 new unit tests verify every template parses, validates, and generates
    at every configured difficulty
  - Hidden ranked set (20 per family in `compactbench/compactbench-hidden`)
    lands in a follow-up so it doesn't commingle public and hidden content
- Submission pipeline + leaderboard (WO-008):
  - `src/compactbench/leaderboard/` — `elite_score` computation, tie-breakers,
    qualification floors (with rejection reasons), `RunResult` → public
    `LeaderboardRow` projection, best-first rank assignment
  - `.github/workflows/evaluate-submission.yml` — runs on GitHub-hosted
    `ubuntu-latest`, gated on a maintainer-applied `evaluate` label; clones PR
    head, installs submission deps, runs `compactbench run`, posts score
    comment, uploads results artifact
  - `.github/workflows/update-leaderboard.yml` — on push under `submissions/**`
    rebuilds `docs/data/leaderboard.json` via `scripts/rebuild_leaderboard.py`
    and commits; triggers the docs Pages redeploy
  - `docs/leaderboard.md` — live table rendered client-side from
    `data/leaderboard.json`, grouped by `(benchmark_version, target_model)`
  - `submissions/_template/` — copy-paste scaffold (method.py, config.yaml,
    requirements.txt, README.md)
  - `compactbench submit` prints a submission checklist (full PR automation
    stays server-side since hidden-set evaluation requires repo secrets)
  - Runner infra decision updated: v1 uses GitHub-hosted runners, not
    self-hosted; migration path preserved
- End-to-end runner (WO-007):
  - `compactbench run --method <spec> --suite <key> --provider <k> --model <m>`
    orchestrates: load suite → generate cases → per case iterate drift cycles
    (compact → evaluate → score) → aggregate → persist results.jsonl
  - Event-log JSONL format: `run_start`, one `case_complete` per case
    streamed, final `run_end` with aggregates
  - `--resume` continues from an existing output file; rejects with
    `ResumeError` if run parameters differ
  - `compactbench score --results` now pretty-prints the run summary from the
    persisted events (reads, not re-scores)
  - `--method` supports `built-in:<key>` and `<path.py>:<ClassName>`
    (loads user compactors from file paths, verifies `Compactor` subclass)
  - Drift cycles extend the transcript with seeded continuation turns; the
    model's continuation response uses only the previous artifact as context
    (that is the drift vector measured)
  - Per-case `CaseResult` captures all cycles, case-level score, and
    `drift_resistance`; run-level aggregates cover overall / drift /
    constraint retention / contradiction / compression
- Real model providers (WO-006):
  - `GroqProvider` — Llama 3.3 70B, Kimi K2, etc. via the `groq` SDK
  - `GoogleAIStudioProvider` — Gemini 2.0 Flash etc. via the `google-genai` SDK
  - `OllamaProvider` — local models via the `ollama` SDK
  - Shared `retry_with_backoff` async helper with exponential + capped delay
  - Per-provider retry predicates: Groq retries `RateLimitError` /
    `APITimeoutError` / `APIConnectionError`; Google retries 429s and 5xxs;
    Ollama retries `httpx.TimeoutException` / `ConnectError` + 429/5xx
    `ResponseError`
  - Config via `COMPACTBENCH_GROQ_API_KEY`,
    `COMPACTBENCH_GOOGLE_AI_STUDIO_API_KEY`, `COMPACTBENCH_OLLAMA_BASE_URL`
  - Cross-provider contract tests ensure identical response shape
  - Real provider SDKs stay optional (`pip install 'compactbench[providers]'`);
    importing a provider without its SDK raises a clean `ProviderError`
- Built-in compactors + mock provider (WO-005):
  - Four baselines in `compactbench.compactors`: `naive-summary`,
    `structured-state`, `hierarchical-summary`, `hybrid-ledger`
  - All inherit async `Compactor` ABC bound to `(provider, model)` at
    construction
  - Shared JSON → `StructuredState` parser with code-fence stripping and
    lenient field coercion
  - `MockProvider` with scripted-sequence + default-response modes and call
    recording for tests
  - Registries: `list_built_ins()` / `get_built_in()` for compactors and
    `list_providers()` / `get_provider_cls()` for providers
  - `compactbench providers list` wired up
- Scoring engine (WO-004):
  - Per-item checks: `contains_normalized`, `forbidden_absent`, `exact`, `set_match`
  - Weighted cycle aggregation per decisions.md §B3 item weights
  - Contradiction detection (item-aware: recall items excluded)
  - Compression ratio via `cl100k_base` tokenizer
  - Drift resistance from cross-cycle scores (clamped to `[0, 1]`)
  - `compactbench score --results results.jsonl` wired up (reads JSONL of
    `{case, artifact, responses}` records, prints per-case + aggregate summary)
- Case generation engine (WO-003):
  - `compactbench.engine.generate_case` — pure function of
    (template, seed, difficulty) → `GeneratedCase`
  - Case-seed derivation from `(suite_version, seed_group, case_slot)` via SHA-256
  - Difficulty policy application (distractor count, paraphrase depth,
    override timing exposed as `difficulty.*` bindings)
  - Distractor-turn generator (seeded, alternating user/assistant)
  - Variable substitution across transcript, ground truth, and evaluation items
  - `compactbench generate --template <key> --seed <int>` command wired up
  - Three regression fixtures pinning the starter templates at seed=42, medium

[Unreleased]: https://github.com/compactbench/compactbench/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/compactbench/compactbench/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/compactbench/compactbench/releases/tag/v0.1.0
