# CompactBench

> **Your agent compacts conversation history before every long turn. Does it do it correctly?** CompactBench is the benchmark that finds out.

[![PyPI version](https://img.shields.io/pypi/v/compactbench.svg)](https://pypi.org/project/compactbench/)
[![Python](https://img.shields.io/pypi/pyversions/compactbench.svg)](https://pypi.org/project/compactbench/)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![CI](https://github.com/compactbench/compactbench/actions/workflows/ci.yml/badge.svg)](https://github.com/compactbench/compactbench/actions/workflows/ci.yml)
[![Docs](https://img.shields.io/badge/docs-compactbench.github.io-black)](https://compactbench.github.io/compactbench/)

Every long-running LLM app eventually compacts its conversation history — summarises it, extracts structured state, runs some ledger. CompactBench hands your compactor an adversarial transcript, replaces the history with whatever your compactor returned, then asks the model probing questions to see what survived.

**Three things make it different from every other LLM benchmark:**

- **We measure the compaction layer, not the model.** MMLU, SWE-bench, and friends feed the model the full context. CompactBench deliberately strips it.
- **Multi-cycle drift.** Methods are evaluated across repeated compact → continue → compact loops, so decay over time is a first-class metric.
- **Hidden ranked set.** Public practice cases for development; hidden templates rotated on version bumps for ranked scoring. Same discipline as MLPerf and SWE-bench.

Everything is deterministic, versioned, and reproducible — same template + seed + version always yields the same case, and every result is stamped with suite / scorer / model / method versions.

## 30-second try

```bash
pip install compactbench
compactbench run --method built-in:hybrid-ledger --suite starter \
                 --provider ollama --model llama3.2
compactbench score --results results.jsonl
```

Any of the four built-in compactors — `naive-summary`, `structured-state`, `hierarchical-summary`, `hybrid-ledger` — works as a `--method` target. Swap `--provider ollama` for `groq` or `google-ai-studio` if you prefer a remote model (set `COMPACTBENCH_GROQ_API_KEY` or `COMPACTBENCH_GOOGLE_AI_STUDIO_API_KEY`).

Already have production code in [LangChain](https://compactbench.github.io/compactbench/integrations/#langchain) or [LlamaIndex](https://compactbench.github.io/compactbench/integrations/#llamaindex)? Wrap it with `compactbench.integrations` — `pip install 'compactbench[langchain]'` or `compactbench[llamaindex]` — and benchmark what you're already running.

## Other useful commands

```bash
# Deterministic single-case inspection
compactbench generate --template buried_constraint_v1 --seed 42

# List suites / providers / built-in compactors
compactbench suites list
compactbench providers list

# Re-score an existing results file without re-running
compactbench score --results results.jsonl
```

## Writing your own compactor

Implement the `Compactor` interface and register it.

```python
from compactbench.compactors import Compactor
from compactbench.contracts import CompactionArtifact, Transcript

class MyCompactor(Compactor):
    name = "my-method"
    version = "0.1.0"

    def compact(self, transcript: Transcript, config: dict) -> CompactionArtifact:
        ...
```

Then run:

```bash
compactbench run --method path/to/my_compactor.py:MyCompactor --suite elite_practice
```

See [docs/writing-a-compactor.md](docs/writing-a-compactor.md) for full details.

## Leaderboard

The public leaderboard is at **[https://compactbench.github.io/compactbench/leaderboard](https://compactbench.github.io/compactbench/leaderboard/)**.

Submissions are evaluated against **hidden** ranked benchmark cases by a maintainer-operated runner. To submit:

1. Write and test your compactor locally against `elite_practice`.
2. Open a PR to [`submissions/`](submissions/) with your method source and config.
3. A maintainer runs it against the hidden set and merges if it qualifies.

See [docs/submitting.md](docs/submitting.md) for the full submission protocol.

## Project status

**v0.1.0 — first public release (2026-04-17).** The v1 stack ships:

- **Core**: DSL parser, case generation, scoring engine, real providers (Groq / Google AI Studio / Ollama)
- **Methods**: four built-in compactors (`naive-summary`, `structured-state`, `hierarchical-summary`, `hybrid-ledger`)
- **Runtime**: end-to-end `compactbench run` with drift cycles, JSONL event log, `--resume`
- **Leaderboard**: PR-based submission flow on GitHub-hosted runners, static site fed by a qualification + ranking core
- **Content**: 15 public Elite practice templates + 15 hidden ranked templates across three launch families (`buried_constraint`, `decision_override`, `entity_confusion`)

See [CHANGELOG.md](CHANGELOG.md) for the full v0.1.0 breakdown. Post-launch work (more template families, framework integrations, shadow evaluation automation, custom domain) is tracked in [GitHub issues](https://github.com/compactbench/compactbench/issues).

## Contributing

Bug reports, template proposals, and new compactors are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md).

Please also read our [Code of Conduct](CODE_OF_CONDUCT.md).

## License

Apache License 2.0 — see [LICENSE](LICENSE).
