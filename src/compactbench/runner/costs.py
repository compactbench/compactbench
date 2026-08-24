"""Provider + model pricing and free-tier catalogues for the ``--estimate`` flag.

Prices are per-million-tokens (USD) and free-tier limits are tokens/day. Values
are snapshots of published rates as of the tagged date below; they drift so
callers should treat the dollar figures as order-of-magnitude guidance, not
invoice-grade estimates.

Updating: change the value, bump ``CATALOGUE_UPDATED``, and cite the source in
the PR that updates it. ``test_costs_catalogue_is_not_stale`` fails once the
catalogue is more than ``MAX_CATALOGUE_AGE_DAYS`` old, and ``format_estimate``
prints the date, so a silently-rotting price table is no longer possible.

Entries marked ``# verified`` were checked against the provider's published
rates on ``CATALOGUE_UPDATED``. Unmarked entries are carried over from an
earlier snapshot and should be re-checked before being quoted.
"""

from __future__ import annotations

from dataclasses import dataclass

CATALOGUE_UPDATED = "2026-08-24"

# `--estimate` output is advisory, but a price table nobody refreshes silently
# becomes wrong. Fail the suite rather than quote rates from an unknown vintage.
MAX_CATALOGUE_AGE_DAYS = 120


@dataclass(frozen=True)
class ModelCost:
    """Per-million-token prices in USD."""

    input_per_mtok: float
    output_per_mtok: float


# (provider_key, model_key) -> ModelCost
# Provider keys match ``Provider.key``; model keys match what users pass via --model.
MODEL_COSTS: dict[tuple[str, str], ModelCost] = {
    # --- Groq --- (https://console.groq.com/settings/billing)
    ("groq", "llama-3.3-70b-versatile"): ModelCost(0.59, 0.79),
    ("groq", "llama-3.1-8b-instant"): ModelCost(0.05, 0.08),
    ("groq", "mixtral-8x7b-32768"): ModelCost(0.24, 0.24),
    # --- Anthropic --- (https://www.anthropic.com/pricing)
    ("anthropic", "claude-opus-5"): ModelCost(5.00, 25.00),  # verified
    ("anthropic", "claude-sonnet-5"): ModelCost(3.00, 15.00),  # verified
    ("anthropic", "claude-haiku-4-5"): ModelCost(1.00, 5.00),  # verified
    ("anthropic", "claude-opus-4-8"): ModelCost(5.00, 25.00),  # verified
    ("anthropic", "claude-fable-5"): ModelCost(10.00, 50.00),  # verified
    # --- OpenAI --- (https://openai.com/api/pricing/)
    ("openai", "gpt-4o-mini"): ModelCost(0.15, 0.60),
    ("openai", "gpt-4o"): ModelCost(2.50, 10.00),
    ("openai", "o1-mini"): ModelCost(3.00, 12.00),
    # --- Google AI Studio --- (free tier; upgrade pricing at https://ai.google.dev/pricing)
    ("google-ai-studio", "gemini-2.0-flash-exp"): ModelCost(0.00, 0.00),
    ("google-ai-studio", "gemini-2.0-flash"): ModelCost(0.10, 0.40),
    ("google-ai-studio", "gemini-1.5-pro"): ModelCost(1.25, 5.00),
    # --- Ollama --- (local, no per-token cost)
    ("ollama", "llama3.2"): ModelCost(0.00, 0.00),
    ("ollama", "llama3.1"): ModelCost(0.00, 0.00),
    ("ollama", "llama3.2:1b"): ModelCost(0.00, 0.00),
    ("ollama", "qwen2.5:1.5b-instruct"): ModelCost(0.00, 0.00),
}


# Daily-token caps on provider free tiers, used to warn users that a planned
# run will exceed the quota and should be sized down or upgraded.
FREE_TIER_DAILY_TOKEN_LIMITS: dict[tuple[str, str], int] = {
    ("groq", "llama-3.3-70b-versatile"): 100_000,
    ("groq", "llama-3.1-8b-instant"): 500_000,
    # Gemini 2.0 Flash experimental has an RPD cap rather than a token cap on
    # the free tier; leave it out of this table so we don't mis-warn.
}


def lookup_cost(provider_key: str, model: str) -> ModelCost | None:
    """Return ``ModelCost`` for a provider/model pair, or None if unknown."""
    return MODEL_COSTS.get((provider_key, model))


def dollars(cost: ModelCost, input_tokens: int, output_tokens: int) -> float:
    """Project total USD cost given token counts."""
    return (input_tokens * cost.input_per_mtok + output_tokens * cost.output_per_mtok) / 1_000_000


def free_tier_daily_limit(provider_key: str, model: str) -> int | None:
    """Return the daily token cap on this provider's free tier, or None if unknown."""
    return FREE_TIER_DAILY_TOKEN_LIMITS.get((provider_key, model))
