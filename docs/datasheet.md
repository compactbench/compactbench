# Datasheet

A datasheet for CompactBench, following the questions in *Datasheets for Datasets*
(Gebru et al.). It covers the generated conversations, the probes, and the results the
leaderboard publishes.

## Motivation

**Why was it created?** To measure how much state AI agents keep when their context is
compacted — not once, but repeatedly, as in a long-running session — under a fixed token
budget, with answers checked mechanically rather than by another model.

**Who maintains it?** The CompactBench maintainers, in the open at
[github.com/compactbench/compactbench](https://github.com/compactbench/compactbench).

## Composition

**What does an instance look like?** A *case* is a generated working conversation (an
opening of about 32k tokens, then about 8k new tokens before each later compaction) split
into cycles, plus structured *probes* asked after each compaction. Probes are single-choice,
select-all, exact-value or list questions with mechanically checkable answers, superseded
("stale") answers and decoy-only ("trap") answers marked.

**What do conversations contain?** People, projects, components, rules, decisions,
ownership, exact figures, ticket boards, scoped policies, shortlists chosen by reference,
and fetched documents that try to change decisions — interleaved with on-topic filler:
source files, logs, test runs, API responses, tickets, chat. Ranked and practice cases are
*mixed sessions* with every family in one conversation.

**Is any of it real?** No. Every name, company, project, figure and message is
procedurally generated from vocabulary lists and sentence templates. Product and vendor
names (databases, clouds, tools) appear as plausible options, not as claims about those
products. No personal data is used.

**How many instances?** The generator is unbounded: any seed gives a case. The public
suites are fixed by seed (`starter`, `practice`, `drills`); the ranked Elite set is sampled
fresh for every ranked run from a private generator.

**Is anything held back?** The ranked generator's worlds — vocabulary, sentence wording and
filler — are private, so ranked cases can't be memorized. The scenario families, scoring
and public worlds are open source, and the public `practice` suite is built the same way
at the same difficulty.

**Are there known errors or noise?** Every family is calibrated before a season opens: a
fixed reader answering from the full conversation must score at least 0.90 in every family,
and answering from nothing at most 0.10. Items that fail are fixed in the generator, not
patched by hand. Scores vary from case to case, so results carry 95% intervals and
overlapping intervals share a rank.

## Collection and generation

**How is the data produced?** By deterministic Python generators
(`compactbench.scenarios`): a seed picks a world, a project and a cast, each family places
its facts and later changes among filler, and probes are derived from the generator's own
record of the truth. The same seed always gives the same case on every platform.

**Who is involved?** No human annotators or crowdworkers. The answer key comes from the
generator; a fixed reader model only answers questions during evaluation.

## Uses

**Intended uses.** Comparing context-compaction methods (summarizers, structured state,
memory systems, provider-native compaction) on how much state they keep across repeated
compaction; diagnosing which kinds of state a method loses; regression-testing an agent's
compaction.

**Uses to avoid.** Treating a score as a general measure of model intelligence or of
summarization quality outside agentic, state-heavy sessions. Training on the public suites
and then reporting public-suite scores as if they were ranked results.

## Distribution

**How is it distributed?** As an Apache-2.0 Python package (`pip install compactbench`) that
generates the public suites locally, plus the public leaderboard data
(`docs/data/leaderboard.json` in the repository). Results files hold scores and
settings only, never conversation text; published hidden-set results also have their
question keys hashed, so they reveal nothing of the private worlds.

## Maintenance

**How is it updated?** In seasons. A season pins the suite and its version, difficulty,
compactions, cases, token budget and reader, and its rows never change after it closes.
Changes that could move scores ship as a new suite version and, for the ranked set, a new
season. See [governance](governance/elite-versions.md) and the changelog.

**How do I report a problem?** Open an issue on GitHub. Questions about an item that
looks wrong are especially welcome: every probe is supposed to be answerable from the full
conversation.
