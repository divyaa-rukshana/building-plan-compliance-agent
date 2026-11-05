import json

from src.agents import eval_batch as eb


def scenarios():
    return json.loads(eb.SCENARIOS.read_text())


def test_there_are_at_least_20_scenarios_including_the_4_1_case():
    sc = scenarios()
    assert len(sc) >= 20 and any("4.1" in s["name"] for s in sc)
    assert all({"expected_route_stricter", "expected_route_default", "supporting_passage", "why"} <= set(s) for s in sc)


def test_every_scenario_passes_under_both_policies_and_nothing_is_falsely_cleared():
    for pol in ("escalate", "stricter"):
        rows = eb.run_all(pol, "stub", scenarios())
        bad = [(r["id"], r["expected"], r["route"]) for r in rows if not r["ok"]]
        m = eb.metrics(rows)
        assert not bad, bad
        assert m["false_clear_rate"] == 0 and m["false_block_rate"] == 0 and m["unverified_answer_rate"] == 0
        assert m["citation_support_rate"] == 1.0 and m["clause_recall"] == 1.0


def test_single_pass_baseline_is_measurably_worse_and_never_clears_what_it_cannot_support(monkeypatch):
    """The L3 deliberate change: one retrieval pass instead of the agent loop."""
    monkeypatch.setenv("AGENT_PLANNER", "single")
    monkeypatch.setenv("AGENT_VERIFY_RETRIES", "0")
    base = eb.metrics(eb.run_all("stricter", "stub", scenarios()))
    monkeypatch.delenv("AGENT_PLANNER")
    monkeypatch.delenv("AGENT_VERIFY_RETRIES")
    full = eb.metrics(eb.run_all("stricter", "stub", scenarios()))
    assert base["route_accuracy"] < 0.6 < full["route_accuracy"] == 1.0
    assert base["false_clear_rate"] == 0.0 and base["clause_recall"] < full["clause_recall"]
