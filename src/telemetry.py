"""L5 cost and token accounting. One place for prices; every model call is priced through compute_step_billing_metrics.

Prices are PLACEHOLDER rates (the team's original matrix) so the stub run shows a non-zero cost. Set PRICE_PROMPT_PER_1K and
PRICE_COMPLETION_PER_1K from the real provider's price list before quoting a cost per 100 runs.
"""
import os
from typing import Any, Dict, Optional

COST_MATRIX_PER_1K = {
    "prompt_tokens": 0.0015,
    "completion_tokens": 0.0020,
}


def price_per_1k() -> Dict[str, float]:
    def _f(name, default):
        try:
            return float(os.environ[name])
        except (KeyError, ValueError):
            return default
    return {"prompt_tokens": _f("PRICE_PROMPT_PER_1K", COST_MATRIX_PER_1K["prompt_tokens"]),
            "completion_tokens": _f("PRICE_COMPLETION_PER_1K", COST_MATRIX_PER_1K["completion_tokens"])}


def compute_step_billing_metrics(prompt_tokens: int, completion_tokens: int,
                                 price_prompt_per_1k: Optional[float] = None,
                                 price_completion_per_1k: Optional[float] = None) -> Dict[str, Any]:
    """Cost of ONE model call (a step). Signature is backward compatible with the original."""
    p = price_per_1k()
    pp = p["prompt_tokens"] if price_prompt_per_1k is None else price_prompt_per_1k
    pc = p["completion_tokens"] if price_completion_per_1k is None else price_completion_per_1k
    total_step_cost = (prompt_tokens / 1000.0) * pp + (completion_tokens / 1000.0) * pc
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "calculated_cost_usd": round(total_step_cost, 6),
        "cost_per_100_runs_estimate": round(total_step_cost * 100.0, 4),
    }
