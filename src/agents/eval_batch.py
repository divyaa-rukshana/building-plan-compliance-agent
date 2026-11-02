"""Batch evaluation of the agents on evaluation/agent_scenarios.json (L3 starter for Member 3).

    python -m src.agents.eval_batch                      # both conflict policies, prints metrics, writes evaluation/agent_report.csv
    python -m src.agents.eval_batch --policy stricter    # one policy
    python -m src.agents.eval_batch --backend chroma     # same scenarios on Member 3's index (CORPUS_BACKEND=chroma)

Metrics (how each is computed):
  route_accuracy            share of scenarios whose route equals the expected route for the policy
  false_clear_rate          share of scenarios routed clear-for-submission although a clear was not expected  (must be 0)
  false_block_rate          share of benign scenarios that were blocked by the input guardrail                  (must be 0)
  clause_recall             share of scenarios whose must_cite clauses were all cited
  citation_support_rate     share of citations whose quote is a contiguous part of the clause text AS FETCHED AGAIN from the
                            corpus (independent of the run-time verifier); this is the groundedness proxy
  ungrounded_citation_rate  1 - citation_support_rate; the hallucination proxy for citations
  unverified_answer_rate    share of runs that returned a non-escalated route although verification had failed (must be 0)
Context relevance and faithfulness of model-written text need a judge model: Member 3 adds those with TruLens.
"""
import argparse
import csv
import json
import os
import re
import statistics as st
import time
from pathlib import Path

from pydantic import ValidationError

from src.schemas import BuildingProposalRequest

from .contract_adapter import from_team_contract
from .corpus_stub import StubCorpus
from .worker import make_corpus, run_proposal
from .config import get_settings

ROOT = Path(__file__).resolve().parent.parent.parent
SCENARIOS = ROOT / "evaluation" / "agent_scenarios.json"
REPORT = ROOT / "evaluation" / "agent_report.csv"


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def run_all(policy: str, backend: str, scenarios):
    os.environ["CONFLICT_POLICY"] = policy
    os.environ["CORPUS_BACKEND"] = backend
    fetch, _ = make_corpus(get_settings())
    rows = []
    for sc in scenarios:
        exp = sc["expected_route_stricter"] if policy == "stricter" else sc["expected_route_default"]
        row = {"id": sc["id"], "name": sc["name"], "policy": policy, "expected": exp}
        try:
            proposal = BuildingProposalRequest(**sc["proposal"])
        except ValidationError:
            rows.append({**row, "route": "rejected_at_ingestion", "ok": sc.get("expect_rejected", False) and exp == "rejected_at_ingestion",
                         "cited": "", "steps": 0, "tool_calls": 0, "wall_s": 0, "cost": 0, "findings": 0, "grounded": 0, "citations": 0})
            continue
        corpus = StubCorpus(exclude=sc["corpus_exclude"]) if sc.get("corpus_exclude") else None
        t = time.perf_counter()
        res = run_proposal(from_team_contract(proposal.model_dump()), f"eval-{sc['id']}", corpus=corpus)
        wall = time.perf_counter() - t
        cited = sorted({c["clause_id"] for f in res["findings"] for c in f["citations"]})
        source = corpus or fetch
        n_cit = n_ok = 0
        for f in res["findings"]:
            for c in f["citations"]:
                n_cit += 1
                p = source.get(c["clause_id"])
                n_ok += bool(p and _norm(c["quote"]) in _norm(p.text))
        ok = res["route"] == exp
        if sc.get("must_cite") and res["findings"]:
            ok = ok and set(sc["must_cite"]) <= set(cited)
        if sc.get("must_not_cite"):
            ok = ok and not (set(sc["must_not_cite"]) & set(cited))
        if "expect_blocked" in sc:
            ok = ok and ((res["status"] == "blocked") == sc["expect_blocked"])
        if "expect_findings" in sc:
            ok = ok and len(res["findings"]) == sc["expect_findings"]
        if "expect_verified" in sc:
            ok = ok and res["verified"] == sc["expect_verified"]
        rows.append({**row, "route": res["route"], "ok": ok, "cited": ";".join(cited), "steps": res["limits_used"]["steps"],
                     "tool_calls": res["limits_used"]["tool_calls"], "wall_s": round(wall, 3), "cost": res["cost"]["total_cost"],
                     "findings": len(res["findings"]), "grounded": n_ok, "citations": n_cit, "status": res["status"], "verified": res["verified"],
                     "must_cite": sc.get("must_cite", [])})
    return rows


def metrics(rows):
    ran = [r for r in rows if r["route"] != "rejected_at_ingestion"]
    n = len(rows)
    cit = sum(r["citations"] for r in rows)
    ok_c = sum(r["grounded"] for r in rows)
    walls = sorted(r["wall_s"] for r in ran) or [0]
    benign = [r for r in ran if r["expected"] == "clear-for-submission"]
    need = [r for r in ran if r.get("must_cite") and r["findings"] > 0]      # every run that produced findings, verified or not
    return {
        "scenarios": n, "route_accuracy": round(sum(r["ok"] for r in rows) / n, 3),
        "false_clear_rate": round(sum(r["route"] == "clear-for-submission" and r["expected"] != "clear-for-submission" for r in rows) / n, 3),
        "false_block_rate": round(sum(r.get("status") == "blocked" for r in benign) / max(1, len(benign)), 3),
        "clause_recall": round(sum(set(r["must_cite"]) <= set(r["cited"].split(";")) for r in need) / max(1, len(need)), 3),
        "citation_support_rate": round(ok_c / cit, 3) if cit else None,
        "ungrounded_citation_rate": round(1 - ok_c / cit, 3) if cit else None,
        "unverified_answer_rate": round(sum(r.get("verified") is False and r["route"] != "specialist-review" for r in ran) / max(1, len(ran)), 3),
        "mean_steps": round(st.mean(r["steps"] for r in ran), 1), "mean_tool_calls": round(st.mean(r["tool_calls"] for r in ran), 1),
        "p50_wall_s": round(walls[len(walls) // 2], 3), "p95_wall_s": round(walls[min(len(walls) - 1, int(len(walls) * 0.95))], 3),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--policy", choices=["escalate", "stricter", "both"], default="both")
    ap.add_argument("--backend", default="stub")
    ap.add_argument("--scenarios", default=str(SCENARIOS))
    a = ap.parse_args()
    scenarios = json.loads(Path(a.scenarios).read_text())
    allrows = []
    for pol in (["escalate", "stricter"] if a.policy == "both" else [a.policy]):
        rows = run_all(pol, a.backend, scenarios)
        allrows += rows
        print(f"\n=== policy={pol} backend={a.backend}")
        for r in rows:
            print(f"  {'ok  ' if r['ok'] else 'FAIL'} #{r['id']:<2d} {r['name'][:52]:52s} expected={r['expected']:20s} got={r['route']}")
        print("  " + json.dumps(metrics(rows)))
    REPORT.parent.mkdir(exist_ok=True)
    with REPORT.open("w", newline="") as f:
        cols = ["id", "name", "policy", "expected", "route", "ok", "cited", "steps", "tool_calls", "wall_s", "cost", "findings", "citations", "grounded"]
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(allrows)
    print(f"\nreport written to {REPORT}")


if __name__ == "__main__":
    main()
