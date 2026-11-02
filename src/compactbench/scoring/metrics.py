"""Run-level metrics computed from per-probe results.

Definitions (also in docs/methodology.md):

- **score** — mean probe score per family, then the mean across families, so
  every family counts equally however many probes it asks. Abstention probes
  (right answer "not stated" or none) count only when missed: answering them
  right earns nothing, since an empty context would too.
- **score CI** — 95% interval from a bootstrap that resamples whole cases within
  each case family (deterministic seed); a mixed case brings all its families along.
- **normalized score** — per family, ``(score - null) / (oracle - null)`` when
  the run carried controls: how much of the achievable range the method kept.
- **drift resistance** — per case, the score on probes asked both after the
  first and after the last compaction, last over first; averaged over cases.
  0.0 when unmeasurable (no drift cycles, or nothing right at cycle 0).
- **decay** — the same probes' score at the first cycle minus the last.
- **stale rate** — share of probes with a superseded answer on offer where
  the reader picked the superseded one.
- **trap rate** — share of probes that offered a decoy-only answer (another
  project's rule, a rejected proposal, an injected instruction) where the
  reader picked it.
- **hallucination rate** — share of "never settled" probes where the reader
  gave a concrete answer instead of "not stated".
"""

from __future__ import annotations

import random
from collections import defaultdict
from statistics import fmean

from compactbench.contracts import (
    CaseResult,
    CategoryMetrics,
    FamilyMetrics,
    ProbeResult,
    RunMetrics,
)
from compactbench.scoring.answers import Arm, counted

BOOTSTRAP_RESAMPLES = 1000
BOOTSTRAP_SEED = 20261101
#: Below this oracle-minus-null gap a family's normalized score is meaningless.
MIN_CONTROL_GAP = 0.05


def _probe_results(case: CaseResult) -> list[ProbeResult]:
    return [r for cycle in case.cycles for r in cycle.probe_results]


Slices = dict[str, list[list[ProbeResult]]]
"""Per family, one list of probe results per case that asked that family's probes."""


def _family_slices(cases: list[CaseResult], cycle: int | None = None) -> Slices:
    """Group probe results by the family that asked them, one slice per case.

    A single-family case contributes one slice to its family; a mixed case
    contributes a slice to every family it contains.
    """
    slices: Slices = defaultdict(list)
    for case in cases:
        if cycle is not None and len(case.cycles) <= cycle:
            continue
        cycles = case.cycles if cycle is None else [case.cycles[cycle]]
        per_family: dict[str, list[ProbeResult]] = defaultdict(list)
        for c in cycles:
            for r in c.probe_results:
                per_family[r.family or case.family].append(r)
        for family, results in per_family.items():
            slices[family].append(results)
    return slices


def _family_score(slices: list[list[ProbeResult]], arm: Arm = "score") -> float | None:
    """Counted mean of ``arm`` over ``slices``; ``None`` for a control arm that wasn't run."""
    if arm != "score" and any(getattr(r, arm) is None for s in slices for r in s):
        return None
    scores = counted((r for s in slices for r in s), arm)
    return fmean(scores) if scores else 0.0


def _macro(groups: Slices) -> float:
    family_scores = [_family_score(slices) or 0.0 for slices in groups.values() if slices]
    return fmean(family_scores) if family_scores else 0.0


def _bootstrap_ci(cases: list[CaseResult]) -> tuple[float, float]:
    """95% interval for the family-balanced score, resampling whole cases.

    Cases are resampled within their case family, and a resampled case brings all
    of its probes along. In a mixed case every family comes from the same
    conversation, so one hard conversation lowers them together; resampling
    families independently would hide that and make the interval too narrow.
    """
    strata: dict[str, list[CaseResult]] = defaultdict(list)
    for case in cases:
        strata[case.family].append(case)
    rng = random.Random(BOOTSTRAP_SEED)
    samples: list[float] = []
    for _ in range(BOOTSTRAP_RESAMPLES):
        resampled = [rng.choice(members) for members in strata.values() for _ in members]
        samples.append(_macro(_family_slices(resampled)))
    samples.sort()
    low = samples[int(0.025 * (len(samples) - 1))]
    high = samples[int(0.975 * (len(samples) - 1))]
    return low, high


def _carried(case: CaseResult) -> tuple[float, float] | None:
    """Score at the first and last cycle on the probes asked at both.

    "Never settled" probes are left out: an artifact that keeps nothing answers
    them correctly every cycle, which would read as perfect retention.
    """
    if len(case.cycles) < 2:
        return None
    first = {r.key: r.score for r in case.cycles[0].probe_results if not r.expects_abstention}
    last = {r.key: r.score for r in case.cycles[-1].probe_results if not r.expects_abstention}
    shared = sorted(first.keys() & last.keys())
    if not shared:
        return None
    return fmean(first[k] for k in shared), fmean(last[k] for k in shared)


def compute_metrics(cases: list[CaseResult]) -> RunMetrics:
    """Aggregate ``cases`` into :class:`RunMetrics`."""
    groups = _family_slices(cases)
    results = [r for case in cases for r in _probe_results(case)]
    cycles = [cycle for case in cases for cycle in case.cycles]

    by_family: dict[str, FamilyMetrics] = {}
    normalized: list[float] = []
    for family in sorted(groups):
        slices = groups[family]
        score = _family_score(slices) or 0.0
        oracle = _family_score(slices, "oracle_score")
        null = _family_score(slices, "null_score")
        norm: float | None = None
        if oracle is not None and null is not None and oracle - null >= MIN_CONTROL_GAP:
            norm = min(1.0, max(0.0, (score - null) / (oracle - null)))
            normalized.append(norm)
        by_family[family] = FamilyMetrics(
            score=score,
            normalized_score=norm,
            oracle_score=oracle,
            null_score=null,
            cases=len(slices),
            probes=sum(len(s) for s in slices),
        )

    by_category_raw: dict[str, list[float]] = defaultdict(list)
    for r in results:
        by_category_raw[r.category].append(r.score)
    by_category = {
        category: CategoryMetrics(score=fmean(scores), probes=len(scores))
        for category, scores in sorted(by_category_raw.items())
    }

    max_cycles = max((len(case.cycles) for case in cases), default=0)
    by_cycle: list[float] = []
    for index in range(max_cycles):
        per_family = [
            fmean(scores)
            for slices in _family_slices(cases, index).values()
            if (scores := counted(r for s in slices for r in s))
        ]
        by_cycle.append(fmean(per_family) if per_family else 0.0)

    carried = [pair for pair in (_carried(case) for case in cases) if pair is not None]
    ratios = [min(1.0, last / first) for first, last in carried if first > 0]
    drift_resistance = fmean(ratios) if ratios else 0.0
    decay = fmean(first - last for first, last in carried) if carried else 0.0

    stale_pool = [r for r in results if r.stale_possible]
    trap_pool = [r for r in results if r.trap_possible]
    abstention_pool = [r for r in results if r.expects_abstention]
    ci_low, ci_high = _bootstrap_ci(cases) if cases else (0.0, 0.0)

    return RunMetrics(
        score=_macro(groups),
        score_ci_low=ci_low,
        score_ci_high=ci_high,
        normalized_score=(
            fmean(normalized) if normalized and len(normalized) == len(groups) else None
        ),
        by_family=by_family,
        by_category=by_category,
        by_cycle=by_cycle,
        drift_resistance=drift_resistance,
        decay=max(-1.0, min(1.0, decay)),
        stale_rate=(sum(r.stale for r in stale_pool) / len(stale_pool)) if stale_pool else 0.0,
        trap_rate=(sum(r.trapped for r in trap_pool) / len(trap_pool)) if trap_pool else 0.0,
        hallucination_rate=(
            sum(1 for r in abstention_pool if r.answered and not r.abstained) / len(abstention_pool)
            if abstention_pool
            else 0.0
        ),
        compression_ratio=fmean(c.compression_ratio for c in cycles) if cycles else 0.0,
        mean_artifact_tokens=fmean(c.artifact_tokens for c in cycles) if cycles else 0.0,
        budget_violations=sum(1 for c in cycles if c.over_budget),
        reader_error_rate=(
            sum(1 for r in results if not r.answered) / len(results) if results else 0.0
        ),
    )
