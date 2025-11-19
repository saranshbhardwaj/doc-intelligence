"""LLM pricing utilities.

Implements per-model token pricing for Anthropic Claude variants (Haiku 4.5, Sonnet 4.5).
Supports dynamic tiering for Sonnet based on prompt size threshold (200K tokens).
Prompt caching pricing (write/read) is stubbed for future use when cache metadata is available.
"""

from __future__ import annotations
from typing import Optional

# Pricing constants ($ per million tokens = MTok)
SONNET_THRESHOLD = 200_000

PRICING = {
    "haiku": {
        "input": 1.0,         # $/MTok
        "output": 5.0,        # $/MTok
        "cache_write": 1.25,  # $/MTok
        "cache_read": 0.10,   # $/MTok
    },
    "sonnet_tier1": {  # ≤ 200K tokens
        "input": 3.0,
        "output": 15.0,
        "cache_write": 3.75,
        "cache_read": 0.30,
    },
    "sonnet_tier2": {  # > 200K tokens
        "input": 6.0,
        "output": 22.5,
        "cache_write": 7.50,
        "cache_read": 0.60,
    },
}


def _per_token(rate_per_mtok: float) -> float:
    """Convert $/MTok to $/token."""
    return rate_per_mtok / 1_000_000.0


def compute_llm_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
    *,
    prompt_cached: bool = False,
    cache_write: bool = False,
    cache_read: bool = False,
    total_prompt_tokens: Optional[int] = None,
) -> float:
    """Compute USD cost for an LLM call.

    Args:
        model: Model name (expects substring 'haiku' or 'sonnet').
        input_tokens: Number of input tokens used.
        output_tokens: Number of output tokens generated.
        prompt_cached: Whether prompt caching feature was involved (future use).
        cache_write: Whether this call wrote a cached prompt.
        cache_read: Whether this call read from a cached prompt.
        total_prompt_tokens: Total size of prompt (for Sonnet tier selection); defaults to input_tokens if not provided.

    Returns:
        Total cost in USD (float rounded to 6 decimals).
    """
    model_lower = model.lower()
    total_prompt_tokens = total_prompt_tokens or input_tokens

    if "haiku" in model_lower:
        pricing_key = "haiku"
    elif "sonnet" in model_lower:
        pricing_key = "sonnet_tier1" if total_prompt_tokens <= SONNET_THRESHOLD else "sonnet_tier2"
    else:
        # Unknown model fallback: assume $0.00001 per token each direction
        return round((input_tokens + output_tokens) * 0.00001, 6)

    rates = PRICING[pricing_key]
    input_cost = input_tokens * _per_token(rates["input"])
    output_cost = output_tokens * _per_token(rates["output"])

    cache_cost = 0.0
    if prompt_cached:
        if cache_write:
            cache_cost += input_tokens * _per_token(rates["cache_write"])  # approximate cost based on prompt size
        if cache_read:
            cache_cost += input_tokens * _per_token(rates["cache_read"])  # approximate read cost

    total = input_cost + output_cost + cache_cost
    return round(total, 6)


__all__ = ["compute_llm_cost"]