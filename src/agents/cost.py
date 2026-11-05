"""L5: tokens and cost per step and per run; report cost per 100 runs and the biggest driver.
Every step is priced by src.telemetry.compute_step_billing_metrics (the single place for prices)."""
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List

from src.telemetry import compute_step_billing_metrics


def estimate_tokens(text: str) -> int:
    return max(1, round(len(text) / 4))   # rough: ~4 characters per token, flagged as estimated


@dataclass
class CostTracker:
    price_prompt_per_1k: float = 0.0
    price_completion_per_1k: float = 0.0
    steps: List[Dict] = field(default_factory=list)

    def record(self, step: str, agent: str, model: str, prompt_tokens: int, completion_tokens: int, estimated: bool,
               latency_ms: float = 0.0):
        m = compute_step_billing_metrics(prompt_tokens, completion_tokens, self.price_prompt_per_1k, self.price_completion_per_1k)
        self.steps.append({"step": step, "agent": agent, "model": model or "stub", "prompt_tokens": prompt_tokens,
                           "completion_tokens": completion_tokens, "cost": m["calculated_cost_usd"], "estimated": estimated,
                           "latency_ms": round(latency_ms, 2)})

    def summary(self) -> Dict:
        return {
            "steps": self.steps,
            "llm_calls": len(self.steps),
            "prompt_tokens": sum(s["prompt_tokens"] for s in self.steps),
            "completion_tokens": sum(s["completion_tokens"] for s in self.steps),
            "total_cost": round(sum(s["cost"] for s in self.steps), 8),
            "estimated": any(s["estimated"] for s in self.steps),
        }


def report(runs: List[Dict]) -> Dict:
    """runs: list of Result.cost dicts. Cost per 100 runs and the largest single driver (by step name)."""
    if not runs:
        return {"runs": 0}
    total = sum(r["total_cost"] for r in runs)
    tokens = defaultdict(int)
    cost = defaultdict(float)
    for r in runs:
        for s in r["steps"]:
            tokens[s["step"]] += s["prompt_tokens"] + s["completion_tokens"]
            cost[s["step"]] += s["cost"]
    key = cost if total > 0 else tokens
    driver = max(key, key=key.get) if key else None
    return {"runs": len(runs), "cost_per_run": total / len(runs), "cost_per_100_runs": total / len(runs) * 100,
            "tokens_per_run": sum(tokens.values()) / len(runs), "largest_driver": driver,
            "driver_basis": "cost" if total > 0 else "tokens (prices are 0)", "by_step_tokens": dict(tokens)}
