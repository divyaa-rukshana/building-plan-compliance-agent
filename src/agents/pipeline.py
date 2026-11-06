"""Entry point for the rq job (src/worker.py::run_agent_pipeline).

Input : BuildingProposalRequest.model_dump()  (what src/api.py enqueues)
Output: the team's result keys (status, decision, primary_reason, findings, execution_trace) plus the full audit record:
        run_id, correlation_id, verified, degraded, conflicts, summary, telemetry, limits_used, corpus_backend, trace.
"""
from typing import Any, Dict, List, Optional
from rq import get_current_job
from .metrics import record_run
from src.schemas import BuildingProposalRequest
from src.telemetry import compute_step_billing_metrics
from .config import get_settings
from .contract_adapter import from_team_contract
from .otel import RunTrace
from .worker import run_proposal

def _team_findings(res: Dict) -> List[Dict]:
    out = []
    for f in res["findings"]:
        out.append({
            "provision_name": f["title"],
            "is_compliant": f["status"] in ("within_limit", "info"),
            "observed_value": f["proposal_value"] or "(not stated in the proposal)",
            "required_limit": f["limit"],
            "finding_details": f["detail"] or f["title"],
            "citations": [{"clause_id": c["clause_id"], "page": c["page"], "extracted_text": c["quote"]} for c in f["citations"]],
            "status": f["status"], "verified": f["verified"], "source": f["source"],
        })
    return out


def _trace_lines(res: Dict) -> List[str]:
    lines = []
    for e in res["trace"]:
        a, t, n = e["agent"], e["type"], e["name"]
        if t == "tool":
            what = e.get("returned") or e.get("found") or e.get("result_keys") or e.get("result") or ""
            lines.append(f"{a}: {n} {e.get('args', {})} -> {what}")
        elif t in ("verify", "guard", "retry", "limit", "result", "llm"):
            extra = {k: v for k, v in e.items() if k not in ("t_ms", "run_id", "correlation_id", "agent", "type", "name", "latency_ms")}
            lines.append(f"{a}: {n} {extra}")
    return lines + res["escalation_path"]


def _telemetry(res: Dict) -> Dict:
    c = res["cost"]
    tot = compute_step_billing_metrics(c["prompt_tokens"], c["completion_tokens"])
    by_tool: Dict[str, float] = {}
    for e in res["trace"]:
        if e["type"] in ("tool", "llm"):                       # model calls are timed too
            by_tool[e["name"]] = round(by_tool.get(e["name"], 0.0) + e["latency_ms"], 2)
    return {
        "run_id": res["run_id"], "correlation_id": res["correlation_id"],
        "llm_calls": c["llm_calls"], "prompt_tokens": c["prompt_tokens"], "completion_tokens": c["completion_tokens"],
        "calculated_cost_usd": c["total_cost"], "cost_per_100_runs_estimate": round(c["total_cost"] * 100, 4),
        "tokens_estimated": c["estimated"], "cost_by_step": c["steps"],
        "steps": res["limits_used"]["steps"], "tool_calls": res["limits_used"]["tool_calls"],
        "wall_s": res["limits_used"]["wall_s"], "latency_ms_by_step_name": by_tool, "price_note": "placeholder rates unless PRICE_* is set",
    }


def to_team_result(res: Dict) -> Dict[str, Any]:
    return {
        "status": "completed",                       # the job finished; `outcome` says how the run ended
        "decision": res["route"],
        "primary_reason": res["reason"],
        "findings": _team_findings(res),
        "execution_trace": _trace_lines(res),
        "run_id": res["run_id"], "correlation_id": res["correlation_id"], "outcome": res["status"],
        "verified": res["verified"], "degraded": res["degraded"], "summary": res["summary"],
        "conflicts": res["conflicts"], "telemetry": _telemetry(res), "limits_used": res["limits_used"],
        "corpus_backend": res["corpus_backend"], "prompt_version": res["prompt_version"], "conflict_policy": res["conflict_policy"],
        "trace": res["trace"], "disclaimer": res["disclaimer"],
    }


def run_pipeline(proposal_dict: dict, correlation_id: Optional[str] = None) -> Dict[str, Any]:
    job = get_current_job()
    run_id = job.id if job else None
    proposal = BuildingProposalRequest(**proposal_dict)       # same contract the API used: catches contract drift
    with RunTrace(run_id, correlation_id, get_settings().prompt_version) as tr:     # D5: one Jaeger trace per run
        res = run_proposal(from_team_contract(proposal.model_dump()), run_id,
                           correlation_id=correlation_id, hook=tr.hook)
        out = to_team_result(res)
        tr.finish(out)
        record_run(out)
    return out