import json
import os

import pytest

from src.agents.cases import CASES, SCENARIOS
from src.agents.config import get_settings
from src.agents.corpus_stub import StubCorpus
from src.agents.llm import LLMUnavailable, LocalStubLLM
from src.agents.worker import run_proposal


def go(name="ex1", policy=None, monkeypatch=None, **kw):
    if policy:
        os.environ["CONFLICT_POLICY"] = policy
    try:
        return run_proposal(CASES[name] if isinstance(name, str) else name, **kw)
    finally:
        os.environ.pop("CONFLICT_POLICY", None)


def tools_called(r):
    return [e["name"] for e in r["trace"] if e["type"] == "tool"]


# -------------------------------------------------- routing (F6, F7)
def test_conflict_escalates_by_default():
    r = go("ex1")
    assert r["route"] == "specialist-review" and r["status"] == "escalated" and r["verified"]
    assert {c["quantity"] for c in r["conflicts"]} >= {"FAR", "setbacks"}
    assert "precedence" in r["reason"]


@pytest.mark.parametrize("case,route", [("ex1", "clear-for-submission"), ("ex2", "clear-for-submission"),
                                         ("ex3", "revise-and-recheck"), ("ex4", "revise-and-recheck"),
                                         ("no-values", "revise-and-recheck"), ("tiny-plot", "specialist-review")])
def test_routes_under_stricter_policy(case, route):
    r = go(case, "stricter")
    assert r["route"] == route and r["verified"]


def test_cannot_answer_cases_escalate_without_searching():
    for case in ("unknown-use", "commercial", "missing-area"):
        r = go(case)
        assert r["route"] == "specialist-review" and r["findings"] == []
        assert "search_corpus" not in tools_called(r)


def test_never_issues_a_determination():
    for case in CASES:
        r = go(case, "stricter")
        text = json.dumps([r["reason"], r["summary"], r["escalation_path"]]).lower()
        for w in ("compliant", "approved", "certified"):
            assert w not in text, (case, w)


# ------------------------------------------- section 4.1 (the difficult case)
def test_case_4_1_finds_and_cites_both_provisions():
    r = go("ex2", "stricter")
    ids = {c["clause_id"] for f in r["findings"] for c in f["citations"]}
    assert "BBMP2003/Table-4" in ids                 # setback table
    assert "BBMP2003/9.10.4" in ids                  # road width lowers FAR, stated away from the setback table
    assert "RMP2015/4.1.2.ii.b" in ids               # height cap by road width
    far = next(f for f in r["findings"] if f["id"] == "far_bylaws")
    assert far["limit"] == "maximum FAR 0.75" and far["verified"]
    cov = next(f for f in r["findings"] if f["id"] == "coverage_bylaws")
    assert "60%" in cov["limit"]


def test_first_search_alone_misses_provisions_the_loop_finds():
    c = StubCorpus()
    first = {p.clause_id for p in c.search("setbacks residential building height 7.5 m plot depth 12 width 9", 3)}
    r = go("ex2", "stricter")
    final = {c_["clause_id"] for f in r["findings"] for c_ in f["citations"]}
    assert not {"BBMP2003/9.10.4", "RMP2015/4.1.2.ii.b"} <= first
    assert {"BBMP2003/9.10.4", "RMP2015/4.1.2.ii.b"} <= final


# ------------------------------------------------ verification (A3)
def test_missing_clause_triggers_retry_then_escalation():
    r = run_proposal(CASES["ex2"], corpus=StubCorpus(**SCENARIOS["missing-clause"]))
    assert r["route"] == "specialist-review" and r["verified"] is False and r["status"] == "escalated"
    assert any("Different strategy" in x for x in r["escalation_path"])
    assert [e for e in r["trace"] if e["name"] == "verification"].__len__() == 2


def test_tampered_answer_is_caught_and_corrected(monkeypatch):
    monkeypatch.setenv("CONFLICT_POLICY", "stricter")
    r = run_proposal(CASES["ex2"], debug="tamper_far")
    v = [e for e in r["trace"] if e["name"] == "verification"]
    assert [e["ok"] for e in v] == [False, True]
    assert next(f for f in r["findings"] if f["id"] == "far_bylaws")["limit"] == "maximum FAR 0.75"


# --------------------------------------------- guardrails (L4)
def test_injection_is_blocked_before_any_agent_or_model():
    llm = LocalStubLLM()
    r = run_proposal(CASES["inject"], llm=llm)
    assert r["status"] == "blocked" and r["route"] == "specialist-review"
    assert not tools_called(r) and llm.calls == [] and r["limits_used"]["steps"] == 0
    assert "compliant" not in r["reason"].lower()


def test_model_summary_with_determination_or_invented_number_is_rejected(monkeypatch):
    monkeypatch.setenv("CONFLICT_POLICY", "stricter")
    for bad in ["The building is compliant with all bye-laws.", "FAR limit is 9.99 so the plan is fine."]:
        r = run_proposal(CASES["ex1"], llm=LocalStubLLM(replies=[bad]))
        assert bad not in r["summary"] and r["summary"]
        assert any(e["name"] == "summary_rejected" for e in r["trace"])


def test_good_model_summary_is_kept(monkeypatch):
    monkeypatch.setenv("CONFLICT_POLICY", "stricter")
    r = run_proposal(CASES["ex1"], llm=LocalStubLLM(replies=["The bye-law FAR limit is 0.75 and the RMP limit is 1.75."]))
    assert r["summary"].startswith("The bye-law FAR limit")


# ----------------------------------------- limits, degradation (A1, A5)
def test_step_limit_ends_run_as_escalation_not_answer(monkeypatch):
    monkeypatch.setenv("AGENT_MAX_STEPS", "4")
    r = run_proposal(CASES["ex1"])
    assert r["route"] == "specialist-review" and r["verified"] is False and r["limits_used"]["steps"] <= 4
    assert "did not finish" in r["reason"]


def test_tool_call_limit(monkeypatch):
    monkeypatch.setenv("AGENT_MAX_TOOL_CALLS", "3")
    r = run_proposal(CASES["ex1"])
    assert r["route"] == "specialist-review" and "tool-call limit" in r["reason"]


def test_wall_clock_limit(monkeypatch):
    monkeypatch.setenv("AGENT_MAX_WALL_S", "0")
    assert run_proposal(CASES["ex1"])["route"] == "specialist-review"


class DownLLM:
    model = "down"
    def complete(self, m, step):
        raise LLMUnavailable("circuit open")


def test_model_down_degrades_to_deterministic_findings_and_escalates(monkeypatch):
    monkeypatch.setenv("CONFLICT_POLICY", "stricter")
    r = run_proposal(CASES["ex1"], llm=DownLLM())
    assert r["degraded"] and r["route"] == "specialist-review" and r["findings"]
    assert "unavailable" in r["reason"]


class BoomCorpus(StubCorpus):
    def search(self, q, k=3):
        raise RuntimeError("index down")


def test_corpus_failure_never_returns_a_confident_answer():
    r = run_proposal(CASES["ex1"], corpus=BoomCorpus())
    assert r["route"] == "specialist-review" and r["verified"] is False


# ----------------------------------------------------- planner (A1)
def test_llm_planner_garbage_falls_back_and_still_completes(monkeypatch):
    monkeypatch.setenv("AGENT_PLANNER", "llm")
    monkeypatch.setenv("CONFLICT_POLICY", "stricter")
    r = run_proposal(CASES["ex2"], llm=LocalStubLLM())
    assert r["route"] == "clear-for-submission"
    assert any(e["name"] == "fallback_to_rule" for e in r["trace"])


def test_llm_planner_cannot_finish_early(monkeypatch):
    monkeypatch.setenv("AGENT_PLANNER", "llm")
    monkeypatch.setenv("CONFLICT_POLICY", "stricter")
    llm = LocalStubLLM(replies=['{"tool": "finish", "args": {}}'] * 30)
    r = run_proposal(CASES["ex2"], llm=llm)
    assert r["verified"] and r["route"] == "clear-for-submission"


# -------------------------------------------- observability, prompts, cost
def test_every_event_carries_the_run_id_and_run_is_reconstructible():
    r = run_proposal(CASES["ex2"], run_id="abc123")
    assert r["run_id"] == "abc123" and all(e["run_id"] == "abc123" for e in r["trace"])
    names = {e["name"] for e in r["trace"]}
    assert {"search_corpus", "get_clause", "verification", "final"} <= names
    assert all("latency_ms" in e for e in r["trace"])


def test_prompt_version_recorded_and_variants_load(monkeypatch):
    assert run_proposal(CASES["ex1"])["prompt_version"] == "v1"
    monkeypatch.setenv("PROMPT_VERSION", "v2")
    assert run_proposal(CASES["ex1"])["prompt_version"] == "v2"


def test_cost_recorded_per_step_and_per_run(monkeypatch):
    monkeypatch.setenv("PRICE_PROMPT_PER_1K", "0.5")
    monkeypatch.setenv("PRICE_COMPLETION_PER_1K", "1.5")
    monkeypatch.setenv("CONFLICT_POLICY", "stricter")
    r = run_proposal(CASES["ex1"])
    c = r["cost"]
    assert c["llm_calls"] == 1 and c["steps"][0]["step"] == "summary" and c["total_cost"] > 0
    assert c["prompt_tokens"] == c["steps"][0]["prompt_tokens"]


def test_cost_report_cost_per_100_runs():
    from src.agents import cost
    runs = [{"total_cost": 0.002, "steps": [{"step": "summary", "prompt_tokens": 100, "completion_tokens": 20, "cost": 0.001},
                                             {"step": "planner", "prompt_tokens": 300, "completion_tokens": 20, "cost": 0.001}]}] * 4
    rep = cost.report(runs)
    assert abs(rep["cost_per_100_runs"] - 0.2) < 1e-9 and rep["largest_driver"] in ("summary", "planner")
