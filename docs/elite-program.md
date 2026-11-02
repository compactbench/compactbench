# Elite program

Elite is CompactBench's ranked track: the hardest set we maintain, and the only one that
produces leaderboard ranks.

## Tracks

| Track | Visibility | Purpose |
|---|---|---|
| **Starter** | public | smoke-test a method end to end (~1.5k-token conversations) |
| **Practice** | public | develop and debug at Elite difficulty (~32k-token openings, 4 drift cycles) |
| **Elite** | hidden | ranked runs |

Practice and Elite share the same families, difficulty profile, probe formats and scoring.
Elite differs in what can't be learned from the public package: its cases are set in
private worlds — their own people, projects, rules, decisions, facts and filler — and
every sentence the families write uses private wording.

## Fresh samples, not a fixed test set

Elite is a generator, not a list of cases. Every ranked run draws its own sample, so
there is no answer key to memorize, and a run's cases — even if a submitter sees them in
their own provider logs — tell them nothing reusable about the next run. Scores are
comparable across samples because the generator is calibrated: one method scored on
several fresh samples lands within a few points, and every reported score carries a
confidence interval.

## What makes it hard

- Rules stated once, indirectly, inside pasted notes or tool output, tens of thousands of
  tokens before they matter — among look-alike rules for other projects, hypotheticals
  and rejected proposals.
- Decisions overridden, reverted and carved into scoped exceptions, across compactions.
- Look-alike people trading ownership back and forth.
- Choices made by reference that only resolve if the alternatives survived.
- Exact figures that get estimated, finalized and corrected, next to near-identical
  figures for sibling projects.
- Rules that cover only some components or only until a date, with scopes that keep
  changing.
- A ticket board whose statuses, owners and blockers move between compactions.
- Fetched documents and injected instructions that contradict what the team decided.
- Questions about things that were raised but never settled, where any concrete answer
  is a hallucination.
- Wrong answers built from the conversation itself, so a lossy summary picks them.
- A fixed token budget for every artifact.

## Fairness

Every item must be answerable from the full conversation and not guessable from
nothing. Each Elite release is checked against both before it is used: items a reader
gets wrong with the full conversation, or right with no context, are removed, and the
families are balanced so no single family is easy. Runs with `--controls` measure the
same ceiling and floor on their own cases.

## Seasons

A season pins every setting that affects a score: suite and version, difficulty, drift
cycles, cases per family, token budget, and the reader model and its reasoning effort.
Season 1 is defined in [`seasons/s1.yaml`](https://github.com/compactbench/compactbench/blob/main/seasons/s1.yaml). Submitters choose only
their method and the model it calls. Leaderboards are segmented by season, and a
season's rows stay pinned to its versions permanently.

See [governance](governance/elite-versions.md) for versioning and retirement.
