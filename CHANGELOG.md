# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/compactbench/compactbench/compare/v0.0.0...HEAD
