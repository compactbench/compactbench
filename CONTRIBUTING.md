# Contributing to CompactBench

Thanks for your interest. This project lives and dies by community submissions of compaction methods and scenario families, so contributions are genuinely welcome.

## Ways to contribute

| Contribution | Entry point |
|---|---|
| Report a bug | [Bug report issue](https://github.com/compactbench/compactbench/issues/new?template=bug_report.md) |
| Propose a new scenario family | [Template proposal issue](https://github.com/compactbench/compactbench/issues/new?template=template_proposal.md) |
| Submit a compaction method for leaderboard scoring | [Submission guide](docs/submitting.md) |
| Improve docs or examples | PR to `docs/` directly |
| Fix something in core | PR to `src/compactbench/` with tests |

## Good places to contribute

- **Run baselines on models we don't cover.** Run the built-in methods and controls on
  `practice` with a model of your choice (`--controls` on) and open a PR with the
  `results.jsonl` files. `compactbench qualify --results <file>` checks a run locally.
- **A new scenario family.** A family is a Python class in
  `src/compactbench/scenarios/families/` that places beats in the conversation and
  registers probes; the four existing families are the reference. A good family targets
  one compaction failure, keeps every probe answerable from the full conversation, and
  builds wrong options from the conversation itself. Open an issue with the failure mode
  first.
- **A new compactor.** Built-in methods live in `src/compactbench/compactors/`.
- **Docs and worked examples.**

Open an issue describing what you want to take on before starting anything substantial,
so we can agree on scope before you spend time. Small fixes need no ceremony — just open
the PR.

## Development setup

CompactBench uses [uv](https://github.com/astral-sh/uv) for dependency management.

```bash
git clone https://github.com/compactbench/compactbench.git
cd compactbench
uv venv
uv pip install -e ".[dev,providers]"
pre-commit install
```

Run the test suite:

```bash
pytest
```

Run linters locally (pre-commit does this automatically on commit):

```bash
ruff check .
ruff format --check .
pyright
```

## Pull request checklist

Before requesting review:

- [ ] `pytest` passes
- [ ] `ruff check` and `ruff format --check` pass
- [ ] `pyright` passes with no new errors
- [ ] New or changed behavior has tests
- [ ] Public API changes are documented in `docs/` and noted in `CHANGELOG.md` under `[Unreleased]`
- [ ] If you added a new dependency, it's justified in the PR description

## Commit style

We follow [Conventional Commits](https://www.conventionalcommits.org/) loosely:

```
feat(scoring): add drift resistance metric
fix(scenarios): keep decoy rules out of the active rule set
docs: clarify hidden-set submission flow
```

Scopes generally match top-level packages in `src/compactbench/`.

## Submitting a compaction method

The process is intentionally PR-based so every leaderboard entry has a visible commit trail.

1. Write your method in a Python file subclassing `Compactor`.
2. Run it locally against the public `practice` suite with `--controls`, and check it with `compactbench qualify`.
3. Open a PR placing your method under `submissions/<your-handle>/<method-name>/`.

Ranked evaluation is currently paused; see [docs/submitting.md](docs/submitting.md).

## Proposing a scenario family

Proposals should:

- Target one compaction failure mode that the existing families don't cover, with a short
  example of a real agent hitting it.
- Keep every probe answerable from the full conversation and not guessable from nothing —
  include an oracle and null run (`--controls`) on a few seeds.
- Build wrong options from the conversation itself, and include a sample case
  (`compactbench generate --family <key> --seed 1 --text`).

The families used for ranked Elite runs are maintained privately and are never contributed
through public PRs.

## Code of Conduct

By participating, you agree to abide by our [Code of Conduct](CODE_OF_CONDUCT.md).

## License

By contributing, you agree that your contributions will be licensed under the Apache License 2.0 (see [LICENSE](LICENSE)).
