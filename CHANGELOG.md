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
