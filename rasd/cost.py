"""Approximate cost of Claude API calls, so every benchmark run can print what it spent."""

# US dollars per one million tokens: (input, output).
# Anthropic's list prices, read from platform.claude.com/docs/en/about-claude/pricing
# on 25 November 2026. Prices change: check that page before relying on these.
PRICES = {
    "claude-haiku-5-5": (0.10, 0.50),  # for prompts up to 100,000 tokens; ours are about 1,000
    "claude-sonnet-5-5": (2.00, 10.00),
}

# Project rule: stop a benchmark run that costs more than this.
MAX_RUN_COST_USD = 1.00


def cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    """Approximate cost in US dollars. The model's thinking is counted in its output tokens."""
    if model not in PRICES:
        raise ValueError(
            f"No price is known for the model '{model}'. Add it to PRICES in rasd/cost.py "
            "so the cost can be printed and the spending limit can work."
        )
    input_price, output_price = PRICES[model]
    return (input_tokens * input_price + output_tokens * output_price) / 1_000_000
