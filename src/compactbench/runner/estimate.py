"""Token + dollar projections for ``compactbench run --estimate``.

Generates every case the run would execute (generation is deterministic and
free) and projects calls and tokens for the three parties that spend money:
the compaction method, the reader, and — with ``--controls`` — the oracle and
null control readers. Deliberately conservative: prompt caching is not
discounted, and methods are assumed to make one call per cycle (multi-call
methods such as ``hierarchical-summary`` cost proportionally more).
"""

from __future__ import annotations

from dataclasses import dataclass

from compactbench.contracts import GeneratedCase
from compactbench.rendering import render_turns
from compactbench.runner.costs import (
    CATALOGUE_UPDATED,
    dollars,
    free_tier_daily_limit,
    lookup_cost,
)
from compactbench.runner.reader import DEFAULT_CHUNK_SIZE, questions_prompt
from compactbench.tokens import count_tokens

_COMPACT_OVERHEAD = 200
_READER_OVERHEAD = 250
_UNBUDGETED_ARTIFACT = 1500
_OUTPUT_PER_PROBE = 60


@dataclass(frozen=True)
class SideEstimate:
    provider_key: str
    model: str
    calls: int
    input_tokens: int
    output_tokens: int
    cost_usd: float | None
    """``None`` when the provider/model pair isn't in the cost catalogue."""


@dataclass(frozen=True)
class EstimateResult:
    total_cases: int
    total_probes: int
    compactor: SideEstimate
    reader: SideEstimate
    controls: SideEstimate | None
    daily_limit: int | None


def _side(provider_key: str, model: str, calls: int, inp: int, out: int) -> SideEstimate:
    cost = lookup_cost(provider_key, model)
    return SideEstimate(
        provider_key=provider_key,
        model=model,
        calls=calls,
        input_tokens=inp,
        output_tokens=out,
        cost_usd=dollars(cost, inp, out) if cost is not None else None,
    )


def estimate_run(
    cases: list[GeneratedCase],
    *,
    provider_key: str,
    model: str,
    reader_provider_key: str,
    reader_model: str,
    budget_tokens: int | None,
    controls: bool,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> EstimateResult:
    """Project calls, tokens and dollars for running ``cases``."""
    artifact = budget_tokens or _UNBUDGETED_ARTIFACT
    c_calls = c_in = c_out = 0
    r_calls = r_in = r_out = 0
    k_calls = k_in = k_out = 0
    probes_total = 0
    for case in cases:
        transcript_so_far = 0
        for spec in case.cycles:
            new_tokens = count_tokens(render_turns(spec.turns))
            transcript_so_far += new_tokens
            c_calls += 1
            c_in += new_tokens + (artifact if spec.cycle > 0 else 0) + _COMPACT_OVERHEAD
            c_out += artifact

            probes_total += len(spec.probes)
            chunks = [
                spec.probes[i : i + chunk_size] for i in range(0, len(spec.probes), chunk_size)
            ]
            for chunk in chunks:
                questions = count_tokens(
                    questions_prompt([(f"Q{i + 1}", p) for i, p in enumerate(chunk)])
                )
                r_calls += 1
                r_in += artifact + questions + _READER_OVERHEAD
                r_out += _OUTPUT_PER_PROBE * len(chunk)
                if controls:
                    k_calls += 2
                    k_in += transcript_so_far + 2 * (questions + _READER_OVERHEAD)
                    k_out += 2 * _OUTPUT_PER_PROBE * len(chunk)

    return EstimateResult(
        total_cases=len(cases),
        total_probes=probes_total,
        compactor=_side(provider_key, model, c_calls, c_in, c_out),
        reader=_side(reader_provider_key, reader_model, r_calls, r_in, r_out),
        controls=_side(reader_provider_key, reader_model, k_calls, k_in, k_out)
        if controls
        else None,
        daily_limit=free_tier_daily_limit(provider_key, model),
    )


def _fmt_int(n: int) -> str:
    return f"{n:,}"


def _fmt_side(label: str, side: SideEstimate) -> list[str]:
    cost = (
        f"~${side.cost_usd:,.2f}"
        if side.cost_usd is not None
        else f"no price for {side.provider_key}/{side.model} in runner/costs.py"
    )
    return [
        f"{label} ({side.provider_key} / {side.model})",
        f"  calls: {_fmt_int(side.calls)}   input: {_fmt_int(side.input_tokens)}   "
        f"output: {_fmt_int(side.output_tokens)}   cost: {cost}",
    ]


def format_estimate(est: EstimateResult) -> str:
    """Render an :class:`EstimateResult` as a plain-text report."""
    lines = [
        "Run plan",
        "--------",
        f"  cases: {est.total_cases}   probes asked: {_fmt_int(est.total_probes)}",
        "",
        *_fmt_side("Compaction method", est.compactor),
        *_fmt_side("Reader", est.reader),
    ]
    if est.controls is not None:
        lines.extend(_fmt_side("Controls (oracle + null)", est.controls))
    costs = [s.cost_usd for s in (est.compactor, est.reader, est.controls) if s is not None]
    if costs and all(c is not None for c in costs):
        total = sum(c for c in costs if c is not None)
        lines += ["", f"Estimated total: ~${total:,.2f} USD (no prompt-caching discount)"]
    lines.append(
        f"Prices as of {CATALOGUE_UPDATED} — verify against the provider before relying on them. "
        "Methods that make several calls per cycle cost proportionally more."
    )
    if est.daily_limit is not None:
        used = est.compactor.input_tokens + est.compactor.output_tokens
        verdict = (
            f"exceeds it by ~{used / est.daily_limit:.1f}x"
            if used > est.daily_limit
            else "fits within it"
        )
        lines.append(
            f"Free-tier daily cap for {est.compactor.model}: {_fmt_int(est.daily_limit)} tokens; "
            f"the method side of this run {verdict}."
        )
    return "\n".join(lines)
