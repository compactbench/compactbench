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

CATALOGUE_UPDATED = "2026-11-01"

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
# Where a provider bills long prompts at a higher rate, the short-prompt rate is
# listed (noted per entry); estimates for very long prompts will undershoot.
MODEL_COSTS: dict[tuple[str, str], ModelCost] = {
    # --- Groq --- (https://console.groq.com/docs/models)
    # The Llama models are now Enterprise-only ("Contact sales"), so unpriced.
    ("groq", "openai/gpt-oss-120b"): ModelCost(0.15, 0.60),  # verified
    ("groq", "openai/gpt-oss-20b"): ModelCost(0.075, 0.30),  # verified
    ("groq", "qwen/qwen3.8-27b"): ModelCost(0.80, 4.00),  # verified (preview model)
    # --- Anthropic --- (https://platform.claude.com/docs/en/about-claude/pricing)
    ("anthropic", "claude-fable-5-1"): ModelCost(10.00, 50.00),  # verified
    ("anthropic", "claude-fable-5"): ModelCost(10.00, 50.00),  # verified
    ("anthropic", "claude-opus-5-5"): ModelCost(4.00, 20.00),  # verified
    ("anthropic", "claude-opus-5"): ModelCost(5.00, 25.00),  # verified
    ("anthropic", "claude-opus-4-8"): ModelCost(5.00, 25.00),  # verified
    ("anthropic", "claude-opus-4-7"): ModelCost(5.00, 25.00),  # verified
    ("anthropic", "claude-opus-4-6"): ModelCost(5.00, 25.00),  # verified
    ("anthropic", "claude-sonnet-5-5"): ModelCost(2.00, 10.00),  # verified
    # The scheduled rise to $3 / $15 on 2026-09-01 was cancelled; $2 / $10 is standard.
    ("anthropic", "claude-sonnet-5"): ModelCost(2.00, 10.00),  # verified
    ("anthropic", "claude-sonnet-4-6"): ModelCost(3.00, 15.00),  # verified
    # Prompts <= 100K tokens; $0.50 / $2.50 above that.
    ("anthropic", "claude-haiku-5-5"): ModelCost(0.10, 0.50),  # verified
    ("anthropic", "claude-haiku-4-5"): ModelCost(1.00, 5.00),  # verified
    # --- OpenAI --- (https://developers.openai.com/api/docs/pricing, Standard tier)
    # gpt-6.x / gpt-5.5 / gpt-5.4: prompts <= 272K tokens; long prompts cost more.
    ("openai", "gpt-6-astra"): ModelCost(10.00, 50.00),  # verified
    ("openai", "gpt-6.1-sol"): ModelCost(2.00, 10.00),  # verified
    ("openai", "gpt-6.1-terra"): ModelCost(1.00, 5.00),  # verified
    ("openai", "gpt-6-luna"): ModelCost(0.10, 0.50),  # verified
    ("openai", "gpt-5.5"): ModelCost(5.00, 30.00),  # verified
    ("openai", "gpt-5.4"): ModelCost(2.50, 15.00),  # verified
    ("openai", "gpt-5.4-mini"): ModelCost(0.75, 4.50),  # verified
    ("openai", "gpt-5.4-nano"): ModelCost(0.20, 1.25),  # verified
    ("openai", "gpt-5"): ModelCost(1.25, 10.00),  # verified
    ("openai", "gpt-5-mini"): ModelCost(0.25, 2.00),  # verified
    ("openai", "gpt-5-nano"): ModelCost(0.05, 0.40),  # verified
    ("openai", "gpt-4.1"): ModelCost(2.00, 8.00),  # verified
    ("openai", "gpt-4.1-mini"): ModelCost(0.40, 1.60),  # verified
    ("openai", "gpt-4o"): ModelCost(2.50, 10.00),  # verified
    ("openai", "gpt-4o-mini"): ModelCost(0.15, 0.60),  # verified
    ("openai", "o3"): ModelCost(2.00, 8.00),  # verified
    ("openai", "o4-mini"): ModelCost(1.10, 4.40),  # verified
    # --- Google AI Studio --- (https://ai.google.dev/gemini-api/docs/pricing, paid tier)
    # Gemini 4 Argon and 3.8 Flash have introductory rates (Argon $2 / $10 through
    # 2026-11-30, 3.8 Flash $0.75 / $3.75 through 2026-12-31); the list prices that
    # follow are used so an estimate never undershoots.
    ("google-ai-studio", "gemini-4-argon"): ModelCost(4.00, 20.00),  # verified
    ("google-ai-studio", "gemini-3.8-flash"): ModelCost(1.50, 7.50),  # verified
    ("google-ai-studio", "gemini-3.5-flash-lite"): ModelCost(0.30, 2.50),  # verified
    ("google-ai-studio", "gemini-3.1-flash-lite"): ModelCost(0.25, 1.50),  # verified
    # Prompts <= 200K tokens; $4.00 / $18.00 above that.
    ("google-ai-studio", "gemini-3.1-pro-preview"): ModelCost(2.00, 12.00),  # verified
    # --- Ollama --- (local, no per-token cost)
    ("ollama", "llama3.2"): ModelCost(0.00, 0.00),
    ("ollama", "llama3.1"): ModelCost(0.00, 0.00),
    ("ollama", "llama3.2:1b"): ModelCost(0.00, 0.00),
    ("ollama", "qwen2.5:1.5b-instruct"): ModelCost(0.00, 0.00),
}


# Daily-token caps on provider free tiers, used to warn users that a planned
# run will exceed the quota and should be sized down or upgraded. Only limits
# confirmed on the provider's published rate-limit page belong here. As of
# CATALOGUE_UPDATED none could be: Groq's page (console.groq.com/docs/rate-limits)
# labels its one table as Developer-plan limits and no longer lists the Llama
# models, and Gemini's pricing page states no per-day token cap for its free tier.
FREE_TIER_DAILY_TOKEN_LIMITS: dict[tuple[str, str], int] = {}


def lookup_cost(provider_key: str, model: str) -> ModelCost | None:
    """Return ``ModelCost`` for a provider/model pair, or None if unknown."""
    return MODEL_COSTS.get((provider_key, model))


def dollars(cost: ModelCost, input_tokens: int, output_tokens: int) -> float:
    """Project total USD cost given token counts."""
    return (input_tokens * cost.input_per_mtok + output_tokens * cost.output_per_mtok) / 1_000_000


def free_tier_daily_limit(provider_key: str, model: str) -> int | None:
    """Return the daily token cap on this provider's free tier, or None if unknown."""
    return FREE_TIER_DAILY_TOKEN_LIMITS.get((provider_key, model))
