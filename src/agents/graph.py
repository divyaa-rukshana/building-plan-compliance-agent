"""LangGraph orchestration: three nodes, two agents, one verification boundary.

    extractor  (Agent 1: ingestion)   input guardrail, classify the use, extract entities           [F3, L4]
        |
    auditor    (Agent 2: auditor)     bounded tool loop (search / get clause / lookup / request fields),
        ^  |                          then one finding per provision with clause citations         [A1, F4, F5]
        |  v
    verifier   (verification layer)   every citation must resolve to retrieved text; on failure one retry
                                      with a different strategy (back to auditor), else escalate;
                                      then summary, routing, output filter, result                  [A3, F6, F7, L4]

If the extractor blocks the input, the run goes straight to the verifier, which returns a blocked result with zero tool calls.
If the auditor fails or hits a limit, the run ends as specialist-review with the evidence gathered; it is never returned as a
confident answer.
"""
import json
import re
import time
from typing import Any, Dict, List, Optional, TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import ValidationError

from src import security as guardrails

from . import rules
from .llm import LLMUnavailable
from .planner import make_planner
from .runtime import LimitExceeded, Runtime
from .schemas import Conflict, EvidenceBundle, Finding, ProposalIn, Result
from .tools import ToolError, Tools
from .verify import build_citations, numbers_in, verify_findings

from pathlib import Path

PROMPTS = Path(__file__).parent / "prompts"


class S(TypedDict, total=False):
    proposal: dict
    p: Any
    blocked: str
    category: str
    ent: dict
    ev: EvidenceBundle
    skip_research: str
    research_done: bool
    report: Any
    findings: list
    reqs: dict
    vrep: Any
    attempt: int
    summary: str
    route: str
    reason: str
    status: str
    verified: bool
    result: dict


def build_graph(rt: Runtime):
    s = rt.s

    # ------------------------------------------------------------ guard
    def guard(state: S):
        raw = state["proposal"]
        try:
            p = ProposalIn(**raw)
        except ValidationError as e:
            rt.emit("extractor", "guard", "schema_reject", errors=e.errors()[:3])
            rt.note("Input guard: proposal failed schema validation; no agent started.")
            return {"blocked": "proposal failed schema validation"}
        screen = guardrails.screen_input(p.use, p.notes)
        rt.emit("extractor", "guard", "input_screen", ok=screen.ok, reasons=screen.reasons)
        if not screen.ok:
            rt.note("Input guard: free text matched a prompt-injection or toxicity rule; the text never reached a model.")
            return {"blocked": "free text rejected by the input guardrail: " + "; ".join(screen.reasons[:2])}
        ev = EvidenceBundle()
        return {"p": p, "ev": ev, "attempt": 0, "research_done": False}

    # ------------------------------------------------------- researcher
    def classify(state: S):
        if state.get("ent"):
            return {}
        p: ProposalIn = state["p"]
        cat = rules.classify_proposal(p)
        ent = p.model_dump()
        ent.pop("notes", None)          # screened free text is used here only; the planner and model never see it
        ent["category"] = cat
        state["ev"].entities = ent
        rt.emit("extractor", "step", "classify", category=cat)
        out = {"ent": ent, "category": cat}
        if cat != "residential":
            out["skip_research"] = (f"use classified as '{cat}'; this version applies the residential rule set only"
                                    if cat != "unknown" else "use could not be matched to any land use in the corpus")
        elif p.area_class is None:
            out["skip_research"] = "area_class is missing"
        if "skip_research" in out:
            rt.note("Researcher: " + out["skip_research"] + "; no retrieval attempted.")
            state["ev"].complete = True
        else:
            ev = state["ev"]
            rt.tools = Tools(rt, ev, ent)
            rt.planner = make_planner(s, ent, ev, rt.llm, rt)
        return out

    def act(state: S):
        ev: EvidenceBundle = state["ev"]
        if state.get("skip_research"):
            return {"research_done": True}
        try:
            rt.check_limits()
            rt.steps += 1
            ev.steps = rt.steps
            a = rt.planner.next_action()
            if a.tool == "finish":
                ev.complete = True
                ev.stop_reason = "checklist covered" if not ev.unresolved else "checklist closed with unresolved clauses"
                rt.emit("auditor", "step", "finish", reason=a.reason, unresolved=ev.unresolved)
                return {"research_done": True}
            rt.emit("auditor", "step", a.tool, args=a.args, reason=a.reason)
            _, new = getattr(rt.tools, a.tool)(**a.args)
            rt.planner.observe(new)
            return {}
        except LimitExceeded as e:
            ev.complete, ev.stop_reason = False, str(e)
            rt.note(f"Researcher stopped: {e}.")
            rt.emit("auditor", "limit", "stopped", reason=str(e))
            return {"research_done": True}
        except ToolError as e:
            rt.note(f"Tool problem: {e}")
            rt.tool_errors = getattr(rt, "tool_errors", 0) + 1
            if rt.tool_errors >= 3:
                ev.complete, ev.stop_reason = False, "repeated tool failures"
                return {"research_done": True}
            return {}

    # --------------------------------------------------------- assessor
    def assess(state: S):
        p: ProposalIn = state["p"]
        ev: EvidenceBundle = state["ev"]
        if state.get("skip_research"):
            report = rules.RuleReport([], [], [], False, state["category"], {})
            if p.area_class is None and state["category"] == "residential":
                report.needs_input = ["area_class (A, B or C from the BDA map, bye-law 9.10.1)"]
                report.out_of_scope = None
            return {"report": report, "findings": [], "reqs": {}}
        report = rules.evaluate(p, state["category"], s.conflict_policy)
        findings, reqs = [], {}
        for c in rules.effective_status(report, s.conflict_policy) if s.conflict_policy in ("bylaws", "rmp") else report.checks:
            cites, _ = build_citations(c.reqs, ev)
            findings.append(Finding(id=c.id, title=c.title, status=c.status, proposal_value=c.proposal_value,
                                    limit=c.limit_text, detail=c.detail, source=c.source, citations=cites))
            reqs[c.id] = c.reqs
        if rt.debug == "tamper_far" and state.get("attempt", 0) == 0:
            f = next((x for x in findings if x.id == "far_bylaws"), None)
            if f and f.citations:
                row = next((l for l in ev.passages[f.citations[0].clause_id].text.split("\n") if "FAR 1.00" in l), None)
                if row:     # an answer that sounds right but cites the wrong row of the table
                    f.limit = "maximum FAR 1.00"
                    f.citations[0] = f.citations[0].model_copy(update={"quote": row})
                    rt.emit("verifier", "debug", "tampered_finding", finding=f.id)
        rt.emit("auditor", "step", "assess", findings=len(findings), conflicts=len(report.conflicts))
        return {"report": report, "findings": findings, "reqs": reqs}

    def verify(state: S):
        ev, findings = state["ev"], state["findings"]
        v = verify_findings(findings, state["reqs"], ev)
        rt.emit("verifier", "verify", "verification", ok=v.ok, attempt=state.get("attempt", 0),
                failures=[f.__dict__ for f in v.failures][:6])
        if not v.ok:
            rt.note("Verification failed for: " + "; ".join(f"{x.finding_id or '?'} ({x.reason})" for x in v.failures[:3]))
        return {"vrep": v}

    # ------------------------------------------------- retry / summary
    def prep_retry(state: S):
        v = state["vrep"]
        ids = sorted({f.clause_id for f in v.failures if f.clause_id})
        rt.planner.retarget(ids)
        rt.note(f"Different strategy: looking the clause(s) up by identifier: {', '.join(ids)}.")
        rt.emit("verifier", "retry", "retarget", clause_ids=ids)
        return {"research_done": False, "attempt": state.get("attempt", 0) + 1}

    def after_assessor(state: S):
        v = state.get("vrep")
        if v is None or v.ok:
            return "summarise"
        ev = state["ev"]
        ids = [f.clause_id for f in v.failures if f.clause_id]
        limit_hit = bool(ev.stop_reason) and "limit" in ev.stop_reason
        if state.get("attempt", 0) < s.verify_retries and ids and not limit_hit:
            return "prep_retry"
        return "summarise"

    def template_summary(state: S) -> str:
        rep, fs = state["report"], state["findings"]
        n_exc = [f.title for f in fs if f.status == "exceeds_limit"]
        parts = [f"{len(fs)} provisions were examined."]
        if n_exc:
            parts.append("Limits exceeded: " + "; ".join(n_exc) + ".")
        if rep.conflicts:
            parts.append("The bye-laws and the RMP give different values for: " + ", ".join(c.quantity for c in rep.conflicts) + ".")
        return " ".join(parts)

    def summarise(state: S):
        if state.get("blocked"):
            return {}
        fs = state.get("findings") or []
        if state.get("skip_research") or not fs:
            return {"summary": ""}
        fallback = template_summary(state)
        v = state.get("vrep")
        if v is not None and not v.ok:
            return {"summary": ""}
        data = json.dumps([{"title": f.title, "status": f.status, "limit": f.limit, "proposal": f.proposal_value} for f in fs])
        tmpl = (PROMPTS / s.prompt_version / "summary.txt").read_text(encoding="utf-8")
        try:
            t_llm = time.perf_counter()
            r = rt.llm.complete([{"role": "system", "content": tmpl.replace("{{FINDINGS}}", data)}], "summary")
            llm_ms = (time.perf_counter() - t_llm) * 1000
            rt.cost.record("summary", "verifier", r.model, r.prompt_tokens, r.completion_tokens, r.estimated, latency_ms=llm_ms)
            rt.emit("verifier", "llm", "summary", latency_ms=llm_ms, prompt_tokens=r.prompt_tokens, completion_tokens=r.completion_tokens)
            text, bad = guardrails.filter_output(r.text.strip(), "")
            allowed = {round(x, 6) for x in numbers_in(data)}
            invented = [x for x in numbers_in(text) if round(x, 6) not in allowed]
            toxic = guardrails.screen_toxicity(text).reasons if text else []      # L4: output toxicity
            if bad or invented or toxic or not text:
                rt.emit("verifier", "guard", "summary_rejected", determination_words=bad, invented_numbers=invented,
                        toxic=bool(toxic))
                rt.note("Model summary rejected by the output filter; a template summary was used.")
                return {"summary": fallback}
            return {"summary": text}
        except LLMUnavailable as e:
            rt.degraded = True
            rt.emit("verifier", "llm", "summary_unavailable", error=str(e)[:160])
            rt.note("Model unavailable: deterministic findings only.")
            return {"summary": fallback}

    # ------------------------------------------------------------ route
    def route(state: S):
        if state.get("blocked"):
            return {"status": "blocked", "route": "specialist-review", "verified": False,
                    "reason": "Request not processed: " + state["blocked"] + ". No agent was run on this text."}
        rep, fs, ev, v = state["report"], state["findings"], state["ev"], state.get("vrep")
        policy = s.conflict_policy
        if state.get("skip_research") and rep.needs_input:
            return {"status": "escalated", "route": "specialist-review", "verified": True,
                    "reason": "Required input is missing: " + "; ".join(rep.needs_input) + "."}
        if state.get("skip_research"):
            return {"status": "escalated", "route": "specialist-review", "verified": True,
                    "reason": f"Outside what this system can answer: {state['skip_research']}. No finding was produced."}
        if rep.needs_input:
            return {"status": "escalated", "route": "specialist-review", "verified": True,
                    "reason": "Required input is missing: " + "; ".join(rep.needs_input) + "."}
        if not ev.complete:
            return {"status": "escalated", "route": "specialist-review", "verified": False,
                    "reason": f"Research did not finish ({ev.stop_reason}); results are incomplete and not returned as an answer."}
        if v is not None and not v.ok:
            bad = sorted({f.finding_id for f in v.failures if f.finding_id})
            return {"status": "escalated", "route": "specialist-review", "verified": False,
                    "reason": ("A finding could not be supported by retrieved text even after a second search strategy: "
                               + ", ".join(bad) + ". Corpus may not cover this case.")}
        if rt.degraded:
            return {"status": "escalated", "route": "specialist-review", "verified": True,
                    "reason": "The model was unavailable; only deterministic findings exist, so a person must review."}
        if rep.exemption:
            return {"status": "escalated", "route": "specialist-review", "verified": True,
                    "reason": "An exemption may apply (bye-law 7.2: the Authority may relax the minimum plot size or width)."}
        if rep.conflicts and policy == "escalate":
            q = "; ".join(f"{c.quantity}: bye-laws {c.bylaws} vs RMP {c.rmp}" for c in rep.conflicts)
            exc = [f.title for f in fs if f.status == "exceeds_limit"]
            extra = (" Limits also exceeded: " + "; ".join(exc) + ".") if exc else ""
            return {"status": "escalated", "route": "specialist-review", "verified": True,
                    "reason": f"Provisions conflict ({q}). The documents disagree and precedence is not established here.{extra}"}
        exc = [f for f in fs if f.status == "exceeds_limit"]
        if exc:
            return {"status": "completed", "route": "revise-and-recheck", "verified": True,
                    "reason": "Limits exceeded: " + "; ".join(f"{f.title} (proposed {f.proposal_value or 'see detail'}, {f.limit})" for f in exc)
                              + "." + (f" Conflict policy '{policy}' applied." if rep.conflicts else "")}
        comparable = ("setbacks", "far", "coverage")
        unchecked = sorted({f.id.split("_")[0] for f in fs if f.status == "info" and f.id.split("_")[0] in comparable})
        if unchecked:
            names = {"setbacks": "setbacks", "far": "floor area (FAR)", "coverage": "ground coverage"}
            return {"status": "completed", "route": "revise-and-recheck", "verified": True,
                    "reason": "The proposal does not state " + ", ".join(names[u] for u in unchecked)
                              + ", so those limits are reported but could not be checked. Add the values and resubmit."}
        checked = [f for f in fs if f.status == "within_limit"]
        return {"status": "completed", "route": "clear-for-submission", "verified": True,
                "reason": f"No limit was exceeded among the {len(checked)} provisions checked against stated values"
                          + (f" (conflict policy '{policy}')" if rep.conflicts else "")
                          + ". This is a pre-check, not a determination; a licensed architect or engineer decides."}

    def finish(state: S):
        rep = state.get("report")
        reason, bad1 = guardrails.filter_output(state["reason"], "Result withheld by the output filter; specialist review required.")
        summary, bad2 = guardrails.filter_output(state.get("summary", "") or "x", "")
        summary = "" if summary == "x" else summary
        if bad1 or bad2:
            rt.emit("verifier", "guard", "output_filtered", words=bad1 + bad2)
        route = state["route"] if not (bad1 or bad2) else "specialist-review"
        fs = state.get("findings") or []
        checked = sum(1 for f in fs if f.status == "within_limit")
        guarded = guardrails.filter_output_determination_token(
            route, all_passed=bool(state.get("verified")) and not any(f.status == "exceeds_limit" for f in fs), checked_findings=checked)
        if guarded != route:     # a clearance the evidence does not support is rewritten, and the rewrite is traced
            rt.emit("verifier", "guard", "clearance_blocked", was=route, now=guarded)
            route = guarded
        conflicts = [Conflict(quantity=c.quantity, bylaws=c.bylaws, rmp=c.rmp, clause_ids=c.clause_ids) for c in (rep.conflicts if rep else [])]
        path = list(rt.path)
        path.append(f"Route: {route}. {reason}")
        ent = dict(state.get("ent") or {})
        res = Result(run_id=rt.run_id, correlation_id=rt.correlation_id, status=state["status"], route=route, reason=reason, verified=bool(state.get("verified")),
                     degraded=rt.degraded, entities=ent, findings=state.get("findings") or [], conflicts=conflicts,
                     escalation_path=[guardrails.filter_output(x, "[removed]")[0] for x in path], summary=summary,
                     prompt_version=s.prompt_version, conflict_policy=s.conflict_policy, cost=rt.cost.summary(),
                     trace=rt.trace,
                     limits_used={"steps": rt.steps, "max_steps": s.max_steps, "tool_calls": rt.tool_calls,
                                  "max_tool_calls": s.max_tool_calls, "wall_s": round(rt.elapsed(), 3), "max_wall_s": s.max_wall_s,
                                  "planner": s.planner})
        rt.emit("verifier", "result", "final", route=route, status=state["status"], verified=res.verified)
        res.trace = rt.trace
        return {"result": res.model_dump()}

    # ------------------------------------------------------------- the three nodes
    def extractor(state: S):
        """Agent 1: ingestion, input guardrail, classification and entity extraction."""
        out = guard(state)
        if out.get("blocked"):
            return out
        return {**out, **classify({**state, **out})}

    def auditor(state: S):
        """Agent 2: one tool-loop step per visit; when research ends, build the findings with their citations."""
        if state.get("research_done"):
            return assess(state)
        out = act(state)
        if not out.get("research_done"):
            return out
        return {**out, **assess({**state, **out})}

    def verifier(state: S):
        """Verification boundary: verify, retry once with another strategy, else summarise, route and finish."""
        if state.get("blocked"):
            d = route(state)
            return {**d, **finish({**state, **d})}
        v = verify(state)
        s2 = {**state, **v}
        if after_assessor(s2) == "prep_retry":
            return {**v, **prep_retry(s2)}
        summ = summarise(s2)
        s3 = {**s2, **summ}
        decision = route(s3)
        s4 = {**s3, **decision}
        return {**v, **summ, **decision, **finish(s4)}

    def after_extractor(state: S):
        return "verifier" if state.get("blocked") else "auditor"

    def after_auditor(state: S):
        return "verifier" if state.get("research_done") else "auditor"

    def after_verifier(state: S):
        return END if state.get("result") else "auditor"

    g = StateGraph(S)
    g.add_node("extractor", extractor)
    g.add_node("auditor", auditor)
    g.add_node("verifier", verifier)
    g.add_edge(START, "extractor")
    g.add_conditional_edges("extractor", after_extractor, {"verifier": "verifier", "auditor": "auditor"})
    g.add_conditional_edges("auditor", after_auditor, {"verifier": "verifier", "auditor": "auditor"})
    g.add_conditional_edges("verifier", after_verifier, {END: END, "auditor": "auditor"})
    return g.compile()


def run(rt: Runtime, payload: Dict) -> Dict:
    graph = build_graph(rt)
    out = graph.invoke({"proposal": payload}, config={"recursion_limit": 6 * rt.s.max_steps + 40})
    return out["result"]
