# CompactBench — technical decisions

The decisions behind benchmark v2 (scorer 3.0.0). The [methodology](../methodology.md) is
the authoritative description of what is measured; this page records *why* it is built
this way.

## Measurement

**A true drift loop.** After the first compaction, a method receives only its previous
artifact plus the turns since then. Earlier turns are never resent. This is how
compaction works in a running agent, and it is the only way multi-cycle decay is real:
under v1 the method got the whole transcript every cycle and could re-derive anything it
had dropped.

**A fixed reader, separate from the method's model.** The model that answers questions is
configured on the run and pinned per season, so the method is the only thing that varies.
Methods may call any model, or none.

**Structured probes, mechanical scoring, no judge.** Every probe is single choice,
select-all, an exact value, or a list of values. Wrong options come from the case (the
superseded value, the other project's rule, the look-alike person), so the structured
format doesn't make questions easier. v1's substring checks penalized correct answers
("we must never deploy on Fridays" failed a check for "deploy on Fridays") and rewarded
hedging; an LLM judge would add cost, bias and version drift to every item.

**Hedging can't pay.** Select-all scores `max(0, (right − wrong) / right)`, and generators
guarantee at least as many wrong options as right ones. Picking several options on a
single-choice probe scores zero.

**Family-balanced headline score.** Families are averaged with equal weight, so a family
that asks many probes can't dominate. Scores carry a bootstrap interval over cases.

**Controls on the same cases.** Oracle (full conversation) and null (nothing) are scored on
the same probes when `--controls` is on, because a score only means something between
them, and because with fresh samples per ranked run a separate control run would be on
different cases.

**Drift excludes "never settled" probes.** An artifact that keeps nothing answers those
correctly every cycle; counting them would score total loss as perfect retention.

**A token budget instead of a compression bonus.** Every run compacts to the same budget
(tiers 1024 / 2048 / 4096, `cl100k_base`, measured on the rendered artifact). Over-budget
text is cut before the reader sees it, and ranked runs reject any over-budget cycle.
Methods compete on what they keep within the same room.

**Turn tags never reach the method.** Tags are generation metadata and some mark the
answer-bearing turn; they are stripped at the compaction boundary.

## Case generation

**Scenario families in Python, not YAML templates.** A family tracks its own state across
cycles (rules added and lifted, decision chains, ownership changes, shortlists) and derives
each cycle's probes from that state, so answers are always correct for that point in the
conversation. A declarative template format couldn't express that without becoming a
programming language.

**Deterministic and platform-stable.** All randomness flows from a seeded RNG with
SHA-256-derived child streams, so the same family, seed, difficulty and cycle count give
the same case anywhere, and adding a draw in one place doesn't shift others.

**On-topic, procedural filler.** Filler (code, tests, logs, API responses, git history,
metrics, notes) is about the same project and people, so topic alone doesn't separate
signal from noise. It is template-generated rather than model-written, so it is free to
redistribute, and it never states a rule, decision or ownership, so every probe stays
answerable from the full conversation.

**Private packs for ranked suites.** The engine is public; a suite pack supplies private
families, vocabulary and filler. Ranked runs draw a fresh sample per run, so there is no
fixed answer key to leak.

## Engineering

- Python 3.12 target, 3.11 minimum; uv; Hatchling; Ruff; Pyright strict; pytest.
- Typer + Rich CLI; pydantic v2 contracts, frozen and `extra="forbid"`.
- Provider SDKs are optional extras. No provider sends sampling parameters by default
  (current Claude and OpenAI reasoning models reject them), so model output is not
  deterministic: results report intervals and traces keep every raw reply.
- Results files hold scores only and are safe to share; traces hold everything and are
  private for hidden suites. Aggregates are recomputed from case events on read, so an
  edited summary line can't change a reported score.
- Results record where each model's calls went (`endpoint_kind`); leaderboards segment on
  it so self-hosted models are never ranked as the hosted model they were run under.
- Apache License 2.0.
