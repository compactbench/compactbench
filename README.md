# CompactBench

> Open benchmark for AI conversation compaction methods.

[![PyPI version](https://img.shields.io/pypi/v/compactbench.svg)](https://pypi.org/project/compactbench/)
[![Python](https://img.shields.io/pypi/pyversions/compactbench.svg)](https://pypi.org/project/compactbench/)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![CI](https://github.com/compactbench/compactbench/actions/workflows/ci.yml/badge.svg)](https://github.com/compactbench/compactbench/actions/workflows/ci.yml)

CompactBench measures whether language models still behave correctly after long conversation history is replaced with a compacted representation. It runs adversarial, deterministic, multi-cycle benchmarks and publishes ranked results on a public leaderboard.

- **Deterministic generation** — same template + seed + version always yields the same case
- **Hidden ranked set** — public practice cases for development, hidden templates for ranked scoring
- **Multi-cycle drift** — methods are evaluated across repeated compact → continue → compact loops
- **State-fidelity scoring** — correctness of retained decisions, constraints, and entities, not output style
- **Versioned everywhere** — benchmark suite, template, scorer, model, and method versions are recorded with every result

## Install

```bash
pip install compactbench
```

Or with uv (recommended for development):

```bash
uv pip install compactbench
```

## Quickstart

Run a built-in compactor against the starter suite using a local Ollama model:

```bash
compactbench run \
  --method built-in:hybrid-ledger \
  --suite starter \
  --provider ollama \
  --model llama3.2
```

Generate a single case deterministically for inspection:

```bash
compactbench generate --template buried_constraint_v1 --seed 42
```

Score an existing results file:

```bash
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

The public leaderboard is at **[compactbench.dev](https://compactbench.dev)**.

Submissions are evaluated against **hidden** ranked benchmark cases by a maintainer-operated runner. To submit:

1. Write and test your compactor locally against `elite_practice`.
2. Open a PR to [`submissions/`](submissions/) with your method source and config.
3. A maintainer runs it against the hidden set and merges if it qualifies.

See [docs/submitting.md](docs/submitting.md) for the full submission protocol.

## Project status

Pre-alpha. Core engine, scoring, runner, and CLI are landed. Three workorders remain before the v1 launch:

| # | Scope | Who can pick it up |
|---|---|---|
| [#5 WO-008](https://github.com/compactbench/compactbench/issues/5) | Submission workflow + public leaderboard site | GH Actions + a little Python |
| [#6 WO-009](https://github.com/compactbench/compactbench/issues/6) | Launch Elite template content (3 families) | YAML authoring — **good starter issue** |
| [#7 WO-010](https://github.com/compactbench/compactbench/issues/7) | Docs polish + PyPI 0.1.0 release | Writers + release-workflow folks |

Each issue has full scope, acceptance criteria, and starter pointers. Comment to claim.

## Contributing

Bug reports, template proposals, and new compactors are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md).

Please also read our [Code of Conduct](CODE_OF_CONDUCT.md).

## License

Apache License 2.0 — see [LICENSE](LICENSE).
