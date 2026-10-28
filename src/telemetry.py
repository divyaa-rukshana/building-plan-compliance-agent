from typing import Dict, Any

COST_MATRIX_PER_1K = {
    "prompt_tokens": 0.0015,     
    "completion_tokens": 0.0020
}

def compute_step_billing_metrics(prompt_tokens: int, completion_tokens: int) -> Dict[str, Any]:
    """Captures runtime metadata consumption boundaries for step cost estimates (L5)."""
    prompt_cost = (prompt_tokens / 1000.0) * COST_MATRIX_PER_1K["prompt_tokens"]
    completion_cost = (completion_tokens / 1000.0) * COST_MATRIX_PER_1K["completion_tokens"]
    total_step_cost = prompt_cost + completion_cost
    
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "calculated_cost_usd": round(total_step_cost, 6),
        "cost_per_100_runs_estimate": round(total_step_cost * 100.0, 4)
    }
