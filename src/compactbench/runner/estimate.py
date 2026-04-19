"""Token + dollar projections for the ``--estimate`` flag.

Generates every case the run would execute (case generation is deterministic
and has no side effects), tokenises the transcripts + evaluation-item prompts,
multiplies by the expected per-call output-token envelope, and reports total
calls, input / output tokens, and a dollar estimate if the provider + model
appear in the cost catalogue.

Deliberately conservative about output-token envelopes — real completions are
bounded by ``CompletionRequest.max_tokens`` but rarely hit it. The constants
below match the medians we've observed across the four built-in baselines on
the Elite practice suite.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import tiktoken

from compactbench.engine import derive_case_seed, generate_case
from compactbench.runner.costs import (
    ModelCost,
    dollars,
    free_tier_daily_limit,
    lookup_cost,
)

if TYPE_CHECKING:
    from compactbench.dsl import DifficultyLevel, TemplateDefinition


# Output-token envelopes (median observed across built-in baselines).
# These are rough but stable enough for sizing decisions.
_ESTIMATED_COMPACT_OUTPUT_TOKENS = 500
_ESTIMATED_EVAL_OUTPUT_TOKENS = 200

# Overheads added to input-token counts to cover prompt templates + system
# messages that sit around the cached content.
_COMPACT_PROMPT_OVERHEAD_TOKENS = 100
_EVAL_PROMPT_OVERHEAD_TOKENS = 80


@dataclass(frozen=True)
class EstimateResult:
    total_cases: int
    total_calls: int
    input_tokens: int
    output_tokens: int
    cost_usd: float | None  # None when provider/model pair isn't in the catalogue
    daily_limit: int | None  # None when the provider's free tier has no token cap
    provider_key: str
    model: str


def _tokeniser() -> tiktoken.Encoding:
    # cl100k_base is a close-enough proxy for modern models; per-provider
    # tokenisers would add variance well below the overall estimate uncertainty.
    return tiktoken.get_encoding("cl100k_base")


def estimate_run(
    *,
    templates: list[TemplateDefinition],
    suite_key: str,
    suite_version: str,
    seed_group: str,
    case_count_per_template: int,
    difficulty: DifficultyLevel,
    drift_cycles: int,
    provider_key: str,
    model: str,
) -> EstimateResult:
    """Project total calls, tokens, and dollars for a planned run."""
    encoding = _tokeniser()

    cycles_per_case = drift_cycles + 1
    total_cases = 0
    total_calls = 0
    total_input = 0
    total_output = 0

    for template in templates:
        # Seed namespace mirrors the runner so estimate uses the exact same
        # cases the real run will execute.
        seed_namespace = f"{suite_key}@{suite_version}/{template.key}@{template.version}"
        for slot in range(case_count_per_template):
            case_seed = derive_case_seed(seed_namespace, seed_group, slot)
            case = generate_case(template, case_seed, difficulty)
            total_cases += 1

            # Compact-call input is the full transcript once per cycle.
            transcript_text = "\n".join(t.content for t in case.transcript.turns)
            transcript_tokens = len(encoding.encode(transcript_text))

            # Evaluation-call input is the artifact (~transcript / 4 after compaction)
            # plus each item's prompt, summed over all items in the cycle.
            eval_input_per_cycle = 0
            for item in case.evaluation_items:
                item_tokens = len(encoding.encode(item.prompt))
                eval_input_per_cycle += (
                    transcript_tokens // 4 + item_tokens + _EVAL_PROMPT_OVERHEAD_TOKENS
                )

            total_calls += cycles_per_case * (1 + len(case.evaluation_items))
            total_input += cycles_per_case * (
                transcript_tokens + _COMPACT_PROMPT_OVERHEAD_TOKENS + eval_input_per_cycle
            )
            total_output += cycles_per_case * (
                _ESTIMATED_COMPACT_OUTPUT_TOKENS
                + _ESTIMATED_EVAL_OUTPUT_TOKENS * len(case.evaluation_items)
            )

    cost = lookup_cost(provider_key, model)
    cost_usd = dollars(cost, total_input, total_output) if cost is not None else None
    daily_limit = free_tier_daily_limit(provider_key, model)

    return EstimateResult(
        total_cases=total_cases,
        total_calls=total_calls,
        input_tokens=total_input,
        output_tokens=total_output,
        cost_usd=cost_usd,
        daily_limit=daily_limit,
        provider_key=provider_key,
        model=model,
    )


def format_estimate(est: EstimateResult) -> str:
    """Render an ``EstimateResult`` as a plain-text report for stdout."""
    lines: list[str] = []
    lines.append("Run plan")
    lines.append("--------")
    lines.append(f"  cases total:     {est.total_cases}")
    lines.append(f"  API calls:       {est.total_calls}")
    lines.append(f"  input tokens:    {_fmt_int(est.input_tokens)}")
    lines.append(f"  output tokens:   {_fmt_int(est.output_tokens)}")
    lines.append("")

    lines.append(f"Cost on {est.provider_key} / {est.model}")
    lines.append("-" * (8 + len(est.provider_key) + 3 + len(est.model)))
    if est.cost_usd is None:
        lines.append(
            f"  (no cost catalogue entry for {est.provider_key}/{est.model} — "
            "update src/compactbench/runner/costs.py to include it)"
        )
    else:
        lines.append(f"  estimated total: ~${est.cost_usd:,.2f} USD")
    lines.append("")

    if est.daily_limit is not None:
        total_tokens = est.input_tokens + est.output_tokens
        lines.append("Free-tier check")
        lines.append("---------------")
        lines.append(
            f"  {est.provider_key} free-tier daily cap for {est.model}: "
            f"{_fmt_int(est.daily_limit)} tokens"
        )
        if total_tokens > est.daily_limit:
            ratio = total_tokens / est.daily_limit
            lines.append(
                f"  this run ({_fmt_int(total_tokens)} tokens) will exceed the cap by ~{ratio:.1f}x"
            )
            lines.append("  options: lower --case-count, upgrade the provider, or switch providers")
        else:
            lines.append("  this run fits within the free-tier daily cap")

    return "\n".join(lines)


def _fmt_int(n: int) -> str:
    return f"{n:,}"


__all__ = ["EstimateResult", "ModelCost", "estimate_run", "format_estimate"]
