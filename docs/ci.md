# Check your method in CI

`compactbench check` runs a small, fixed sample of the public Practice suite on your
compaction method and tells you whether it forgets more than it used to. Put it in CI and a
pull request that makes your agent lose instructions, decisions or exact figures after
compaction fails its build, with a report of what got worse.

Every call uses **your own API keys**: your method's model and the reader that answers the
questions.

## What it runs

By default the check uses the Season 1 settings on a small sample:

| Setting | Default | Option |
|---|---|---|
| Suite | `practice` (mixed sessions at Elite difficulty, ~32k-token openings) | `--suite` |
| Cases | 4 | `--cases` |
| Which cases | seed group `ci`, the same cases every run | `--seed-group` |
| Compactions | 5 (the opening plus 4 drift cycles) | |
| Budget | 1,024 tokens per artifact | `--budget` |
| Method's model | `anthropic` / `claude-haiku-5-5` | `--provider`, `--model` |
| Reader | `anthropic` / `claude-haiku-5-5`, high effort | `--reader-provider`, `--reader-model`, `--reader-effort` |

Because the cases never change, a change in score comes from your method (and the run-to-run
variation of the models), not from a different sample. See the cost of a run before making any
calls:

```bash
compactbench check --method my_compactor.py:MyCompactor --estimate
```

With Claude Haiku 5.5 as both the method's model and the reader, a default run of the
`sectioned-summary` baseline made 80 calls and cost about $0.11, most of it the reader's
thinking (which the estimate doesn't include).

## Run it locally

```bash
pip install 'compactbench[providers]'
export COMPACTBENCH_ANTHROPIC_API_KEY=...

# Record a baseline once, and commit it.
compactbench check --method my_compactor.py:MyCompactor \
                   --baseline .compactbench/baseline.json --update-baseline

# Later: compare against it. Exits 1 on a regression.
compactbench check --method my_compactor.py:MyCompactor \
                   --baseline .compactbench/baseline.json
```

The report shows the score with its 95% interval, the score after each compaction (how fast the
method forgets) and the score per [failure family](methodology.md), each against the baseline.
`--summary FILE` appends the same report as Markdown, `--json FILE` writes the numbers and the
verdict, and `--output` keeps the full results file for `compactbench score`.

## The gates

| Gate | Default | Fails when |
|---|---|---|
| `--max-drop` | 5 points | the score is more than this many points (0-100 scale) below the baseline |
| `--min-score` | off | the score is below this |

A baseline only counts if it was recorded with the same suite version, cases, seed group,
budget, reader and scorer. If any of them differ the check fails and asks you to record a new
baseline, rather than reporting a change that means nothing. Changing the method or its model is
fine: that is what you are comparing.

## GitHub Action

```yaml
name: CompactBench

on:
  pull_request:

permissions:
  contents: read
  pull-requests: write # only needed for `comment: true`

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: compactbench/compactbench@main # pin a release tag or commit SHA
        with:
          method: my_compactor.py:MyCompactor
          baseline: .compactbench/baseline.json
          comment: true
        env:
          COMPACTBENCH_ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
```

The report goes to the job summary and, with `comment: true`, to one pull-request comment per
method and model that later runs update. The action installs CompactBench in its own virtual
environment; if your method needs other packages, list them in `install` (for example
`install: -r requirements.txt` or `install: .`).

| Input | Default | |
|---|---|---|
| `method` | required | `built-in:<key>` or `<path.py>:<ClassName>` |
| `provider`, `model` | `anthropic`, `claude-haiku-5-5` | the method's model |
| `reader-provider`, `reader-model`, `reader-effort` | `anthropic`, `claude-haiku-5-5`, `high` | the reader |
| `suite`, `cases`, `seed-group`, `budget` | `practice`, `4`, `ci`, `1024` | the sample |
| `method-config` | `{}` | JSON passed to the method as `self.config` |
| `baseline`, `max-drop`, `min-score` | none, `5`, none | the gates |
| `update-baseline` | `false` | write the run to `baseline` instead of comparing |
| `comment`, `github-token` | `false`, the job's token | the pull-request comment |
| `install` | none | extra `pip install` arguments for your method |
| `version` | the action's own | a CompactBench version from PyPI |
| `python-version`, `working-directory` | `3.12`, `.` | |

Outputs: `score`, `change` (points against the baseline), `passed`, `report` (the JSON report)
and `results` (the full results file — upload it with `actions/upload-artifact` to inspect a
failing run).

Pass each provider's key as an environment variable, as above (`COMPACTBENCH_OPENAI_API_KEY`,
`COMPACTBENCH_GROQ_API_KEY`, ...; see [getting started](getting-started.md#configure-a-provider)).
GitHub does not give repository secrets to workflows triggered from forks, so the check can only
run on pull requests from branches in your repository.

## Choosing the sample size and the gate

Four cases keep the check cheap. The cases are the same every run, so what varies between runs
is the models' sampling. Two identical default runs of the `sectioned-summary` baseline scored
46.8 and 45.7 overall, while single families moved by up to 23 points: gate on the overall
score, and read the family table as a pointer to where to look.

The 95% interval in the report is wider than that (about ±10 points with four cases) because it
also covers which cases were drawn; it tells you how far the score generalizes beyond these
cases. To tighten it, raise `--cases` and record a new baseline. Either way the check measures
your method on public cases: it is a development signal, not a leaderboard score. Ranked scores
come from the hidden Elite set.
