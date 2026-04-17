# Contributing to CompactBench

Thanks for your interest. This project lives and dies by community submissions of compaction methods and benchmark templates, so contributions are genuinely welcome.

## Ways to contribute

| Contribution | Entry point |
|---|---|
| Report a bug | [Bug report issue](https://github.com/UsernameLoad/compactbench/issues/new?template=bug_report.md) |
| Propose a new benchmark template family | [Template proposal issue](https://github.com/UsernameLoad/compactbench/issues/new?template=template_proposal.md) |
| Submit a compaction method for leaderboard scoring | [Submission guide](docs/submitting.md) |
| Improve docs or examples | PR to `docs/` directly |
| Fix something in core | PR to `src/compactbench/` with tests |

## Development setup

CompactBench uses [uv](https://github.com/astral-sh/uv) for dependency management.

```bash
git clone https://github.com/UsernameLoad/compactbench.git
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
fix(dsl): reject templates with duplicate variable names
docs: clarify hidden-set submission flow
```

Scopes generally match top-level packages in `src/compactbench/`.

## Submitting a compaction method

The process is intentionally PR-based so every leaderboard entry has a visible commit trail.

1. Write your method in a Python file subclassing `Compactor`.
2. Run it locally against the `elite_practice` public suite; iterate until you're happy.
3. Open a PR placing your method source under `submissions/<your-handle>/<method-name>/`.
4. A maintainer will label the PR for evaluation. The hidden-set runner executes your method against Elite Ranked cases and posts scores back to the PR.
5. If your method qualifies (see [docs/methodology.md](docs/methodology.md)), the PR is merged and the leaderboard updates.

See [docs/submitting.md](docs/submitting.md) for the full protocol, including the exact artifact shape your method must return.

## Proposing a benchmark template

Template proposals should:

- Target one of the adversarial failure modes described in [docs/elite-program.md](docs/elite-program.md), or propose a new mode with justification.
- Include a sample seed and its generated output so reviewers can sanity-check determinism.
- Validate against `benchmarks/schemas/template-v1.json`.

Hidden ranked templates are never contributed through public PRs. If you have a proposal for a ranked template, open an issue describing the idea at a high level — a maintainer will coordinate a private review.

## Code of Conduct

By participating, you agree to abide by our [Code of Conduct](CODE_OF_CONDUCT.md).

## License

By contributing, you agree that your contributions will be licensed under the Apache License 2.0 (see [LICENSE](LICENSE)).
