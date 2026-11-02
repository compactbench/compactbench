# Elite governance

## Versioning

- Every family has a version; every suite has a version; the scorer has a version.
- A change that can move scores — new or changed families, filler, vocabulary,
  difficulty, probe formats or scoring — is a new suite or scorer version.
- Results record all of them, and leaderboards segment on suite, scorer, reader and
  budget, so numbers from different versions never compete.

| Scorer | Benchmark | Status |
|---|---|---|
| 3.0.0 | v2 — scenario families, true drift loop, structured probes | current |
| 2.0.0 | v1 YAML templates, substring checks | retired; results archived in `docs/data/archive/` |
| 1.0.0 | v1 | retired |

## Seasons

A season fixes one Elite configuration for a period. Within a season, every ranked run
uses the same settings and a fresh sample from the same generator. A new season can
change any setting; its rows form a new board and earlier seasons stay as they were.

## Retirement

A family, generator or season is retired when it is compromised (its private content
leaks) or saturated (top methods score near the oracle ceiling). Retirement is announced
in the changelog; retired content stays available for audit but no new ranked runs use it.

## Review of published runs

Ranked runs are published when they qualify. The maintainers may review any run
afterwards — for example one whose family scores look implausible — against its sealed
traces, and remove it if it breaks the submission rules.
