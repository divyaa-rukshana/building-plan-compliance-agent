"""D5: Prometheus metrics for agent runs. Scraped from the worker on port 8002."""
import logging

from prometheus_client import Counter, Histogram

log = logging.getLogger("agents")

RUNS = Counter("agent_runs_total", "Agent runs", ["route", "outcome"])
TOKENS = Counter("agent_tokens_total", "Model tokens used", ["kind"])
COST = Counter("agent_cost_usd_total", "Model cost in USD (placeholder rates unless PRICE_* is set)")
TOOL_CALLS = Counter("agent_tool_calls_total", "Tool calls made by agents")
RUN_SECONDS = Histogram("agent_run_seconds", "Wall time of one run",
                        buckets=(0.1, 0.25, 0.5, 1, 2, 5, 10, 30, 60))
STEP_SECONDS = Histogram("agent_step_seconds", "Latency per step name", ["step"],
                         buckets=(0.005, 0.01, 0.05, 0.1, 0.5, 1, 5))


def record_run(out: dict):
    """Call once per finished run with the dict from to_team_result. Never raises."""
    try:
        t = out.get("telemetry", {})
        RUNS.labels(route=str(out.get("decision", "")), outcome=str(out.get("outcome", ""))).inc()
        TOKENS.labels(kind="prompt").inc(int(t.get("prompt_tokens", 0)))
        TOKENS.labels(kind="completion").inc(int(t.get("completion_tokens", 0)))
        COST.inc(float(t.get("calculated_cost_usd", 0.0)))
        TOOL_CALLS.inc(int(t.get("tool_calls", 0)))
        RUN_SECONDS.observe(float(t.get("wall_s", 0.0)))
        for step, ms in t.get("latency_ms_by_step_name", {}).items():
            STEP_SECONDS.labels(step=step).observe(float(ms) / 1000.0)
    except Exception:
        log.exception("metrics record failed")