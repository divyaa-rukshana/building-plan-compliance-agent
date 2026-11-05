import json
import logging

from src.agents.cost import CostTracker, report
from src.agents.worker import run_proposal
from src.telemetry import compute_step_billing_metrics
from tests.test_team_pipeline import BASE
from src.agents.contract_adapter import from_team_contract


def test_step_cost_formula_and_original_signature():
    m = compute_step_billing_metrics(1000, 1000)
    assert m == {"prompt_tokens": 1000, "completion_tokens": 1000, "calculated_cost_usd": 0.0035, "cost_per_100_runs_estimate": 0.35}


def test_prices_can_be_set_from_the_environment(monkeypatch):
    monkeypatch.setenv("PRICE_PROMPT_PER_1K", "1")
    monkeypatch.setenv("PRICE_COMPLETION_PER_1K", "2")
    assert compute_step_billing_metrics(1000, 500)["calculated_cost_usd"] == 2.0


def test_tracker_prices_every_step_through_telemetry():
    t = CostTracker(0.0015, 0.0020)
    t.record("summary", "verifier", "m", 50, 10, False)
    t.record("planner", "auditor", "m", 200, 20, True)
    s = t.summary()
    assert s["prompt_tokens"] == 250 and s["estimated"] is True
    assert s["steps"][0]["cost"] == compute_step_billing_metrics(50, 10)["calculated_cost_usd"]
    assert abs(s["total_cost"] - sum(x["cost"] for x in s["steps"])) < 1e-9


def test_cost_report_per_100_runs_and_largest_driver():
    runs = [{"total_cost": 0.002, "steps": [{"step": "summary", "prompt_tokens": 100, "completion_tokens": 20, "cost": 0.0005},
                                             {"step": "planner", "prompt_tokens": 300, "completion_tokens": 20, "cost": 0.0015}]}] * 4
    rep = report(runs)
    assert abs(rep["cost_per_100_runs"] - 0.2) < 1e-9 and rep["largest_driver"] == "planner"


def test_every_log_line_is_json_with_run_and_correlation_id(caplog):
    lg = logging.getLogger("agents")
    lg.addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.INFO, logger="agents"):
            r = run_proposal(from_team_contract(BASE), "run-log1", correlation_id="corr-log1")
    finally:
        lg.removeHandler(caplog.handler)
    lines = [json.loads(rec.getMessage()) for rec in caplog.records if rec.name == "agents"]
    assert lines and all(l["run_id"] == "run-log1" and l["correlation_id"] == "corr-log1" for l in lines)
    assert {"agent", "type", "name", "latency_ms", "t_ms"} <= set(lines[0])
    assert len(lines) == len(r["trace"])                       # the log and the returned trace are the same record


def test_the_container_log_handler_writes_json_to_stdout():
    lg = logging.getLogger("agents")
    assert any(isinstance(h, logging.StreamHandler) for h in lg.handlers) and lg.level == logging.INFO and lg.propagate is False


def test_model_call_latency_is_measured_per_step_and_in_the_trace():
    from src.agents.llm import LocalStubLLM
    r = run_proposal(from_team_contract(BASE), "run-lat", llm=LocalStubLLM(delay_s=0.06))
    step = next(s for s in r["cost"]["steps"] if s["step"] == "summary")
    ev = next(e for e in r["trace"] if e["type"] == "llm")
    assert step["latency_ms"] >= 55 and ev["latency_ms"] >= 55
