"""Constructors for structured probes with seeded option order.

Option order is seeded by the probe key, so a carried probe keeps the same
order every cycle unless its options change. "Not stated" is always the last
option of a single-choice probe, so declining to answer is always possible
and never position-biased.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from compactbench.contracts import NOT_STATED, Probe, ProbeCategory, ProbeFormat, ValueKind
from compactbench.scenarios.rng import Rng


def _dedupe(items: Iterable[str], exclude: Iterable[str] = ()) -> list[str]:
    seen = set(exclude)
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def single(
    rng: Rng,
    *,
    key: str,
    category: ProbeCategory,
    question: str,
    correct: str,
    distractors: Sequence[str],
    stale: Sequence[str] = (),
    traps: Sequence[str] = (),
    origin_cycle: int,
    options: int,
) -> Probe:
    """A single-choice probe.

    ``options`` is the total count including "not stated". Stale answers are
    always kept as options (they are the point); ``distractors`` fill the rest
    in the order given. ``correct`` may be :data:`NOT_STATED`.
    """
    real = [] if correct == NOT_STATED else [correct]
    stale_opts = _dedupe(stale, exclude=[*real, NOT_STATED])
    trap_opts = _dedupe(traps, exclude=[*real, *stale_opts, NOT_STATED])
    room = max(options - 1 - len(real) - len(stale_opts) - len(trap_opts), 0)
    fillers = _dedupe(distractors, exclude=[*real, *stale_opts, *trap_opts, NOT_STATED])[:room]
    body = rng.child(f"options:{key}").shuffled([*real, *stale_opts, *trap_opts, *fillers])
    return Probe(
        key=key,
        category=category,
        format=ProbeFormat.SINGLE,
        question=question,
        options=[*body, NOT_STATED],
        answer=[correct],
        stale=stale_opts,
        traps=trap_opts,
        origin_cycle=origin_cycle,
    )


def multi(
    rng: Rng,
    *,
    key: str,
    category: ProbeCategory,
    question: str,
    correct: Sequence[str],
    wrong: Sequence[str],
    stale: Sequence[str] = (),
    traps: Sequence[str] = (),
    origin_cycle: int,
    max_options: int,
) -> Probe:
    """A select-all-that-apply probe. ``stale`` options are wrong but were once right."""
    right = _dedupe(correct)
    stale_opts = _dedupe(stale, exclude=right)
    trap_opts = _dedupe(traps, exclude=[*right, *stale_opts])
    # Never fewer wrong options than right ones, so selecting everything can't
    # score well: (right - wrong) / right reaches 0 when they're equal.
    total = max(max_options, 2 * len(right))
    room = max(total - len(right) - len(stale_opts) - len(trap_opts), 0)
    fillers = _dedupe(wrong, exclude=[*right, *stale_opts, *trap_opts])[:room]
    return Probe(
        key=key,
        category=category,
        format=ProbeFormat.MULTI,
        question=question,
        options=rng.child(f"options:{key}").shuffled([*right, *stale_opts, *trap_opts, *fillers]),
        answer=right,
        stale=stale_opts,
        traps=trap_opts,
        origin_cycle=origin_cycle,
    )


def value(
    *,
    key: str,
    category: ProbeCategory,
    question: str,
    answer: str,
    kind: ValueKind,
    stale: Sequence[str] = (),
    traps: Sequence[str] = (),
    origin_cycle: int,
) -> Probe:
    """An exact-value probe. ``answer`` may be :data:`NOT_STATED`."""
    return Probe(
        key=key,
        category=category,
        format=ProbeFormat.VALUE,
        question=question,
        answer=[answer],
        value_kind=kind,
        stale=_dedupe(stale, exclude=[answer]),
        traps=_dedupe(traps, exclude=[answer, *stale]),
        origin_cycle=origin_cycle,
    )


def values(
    *,
    key: str,
    category: ProbeCategory,
    question: str,
    answers: Sequence[str],
    kind: ValueKind,
    stale: Sequence[str] = (),
    origin_cycle: int,
) -> Probe:
    """A list probe: every value in ``answers``, nothing else."""
    right = _dedupe(answers)
    return Probe(
        key=key,
        category=category,
        format=ProbeFormat.LIST,
        question=question,
        answer=right,
        value_kind=kind,
        stale=_dedupe(stale, exclude=right),
        origin_cycle=origin_cycle,
    )
