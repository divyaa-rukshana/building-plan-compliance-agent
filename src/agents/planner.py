"""The Researcher's decision policy: what to call next.

RulePlanner (default): deterministic, so tests and load tests are repeatable.
  1. read the request fields
  2. search for the provision that appears to apply (setbacks)
  3. MODIFIER STEP: scan what was retrieved for hints that other provisions modify it (road width, Table references,
     "height") and derive NEW queries from that text, not from the request
  4. checklist: every topic the entities require must have its clauses in evidence; a gap triggers a search with a
     different strategy (topic query, then lookup by clause id); a clause that cannot be found is recorded as unresolved
LLMPlanner: asks the model for the next action as JSON; invalid, unsafe or premature answers fall back to RulePlanner.
"""
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set

from .schemas import EvidenceBundle

B, R = "BBMP2003", "RMP2015"


@dataclass
class Action:
    tool: str
    args: Dict = field(default_factory=dict)
    reason: str = ""


def topics_for(ent: Dict) -> Dict[str, List[str]]:
    """The checklist: topic -> clause ids that must be in evidence for this proposal."""
    zone_tbl = f"{R}/Table-10" if ent.get("zone", "R_MAIN") == "R_MAIN" else f"{R}/Table-12"
    t = {
        "setbacks": [f"{B}/Table-4", f"{B}/Note-3"] + ([f"{B}/Table-5"] if ent["height_m"] > 9.5 else []) +
                    ([f"{R}/Table-9"] if ent["height_m"] > 11.5 else [f"{R}/Table-8"]),
        "coverage_far": [f"{B}/Table-6", f"{B}/9.10.4", f"{B}/9.10.5", f"{B}/9.10.7"],
        "road_def": [f"{B}/2.70"],
        "height": [f"{R}/4.1.2.ii.b", f"{B}/15.1"],
        "zone_limits": [zone_tbl, f"{R}/3.4.iii", f"{R}/3.4.iv"],
    }
    if ent["storeys"] >= 5:
        t["high_rise"] = [f"{B}/2.46", f"{B}/9.3.2", f"{B}/9.3.3"]
    if ent.get("dwelling_type") == "multi" and ent.get("zone", "R_MAIN") == "R_MAIN":
        t["apartments"] = [f"{R}/4.1.2.ii.c"]
    if (ent.get("plot_area_sqm") or ent["plot_width_m"] * ent["plot_depth_m"]) < 50 or ent["plot_width_m"] < 6:
        t["exemption"] = [f"{B}/7.2"]
    return t


def topic_query(topic: str, ent: Dict) -> str:
    return {
        "setbacks": f"setbacks residential building height {ent['height_m']:g} m plot depth {ent['plot_depth_m']:g} width {ent['plot_width_m']:g}",
        "coverage_far": "coverage and FAR by plot area and road width table residential area A B C",
        "road_def": "definition of road width",
        "height": "maximum height restricted when road width is less than 9 m storeys",
        "zone_limits": "FAR and ground coverage Residential zone plot size road width table",
        "high_rise": "high rise building minimum road width and site dimension",
        "apartments": "multi dwelling units apartments plot size ring road width",
        "exemption": "plot less than 50 sqm or width less than 6 metres Authority may relax",
    }[topic]


# hints: text pattern in a retrieved passage -> follow-up actions it suggests (the modifier step)
_HINTS = [
    (re.compile(r"road width|width of (the )?roads?|widths of roads|width of the street", re.I),
     [Action("search_corpus", {"query": "FAR applicable when site does not face road of required width corresponding width"},
             "retrieved text makes a limit depend on road width; look for provisions that modify it"),
      Action("search_corpus", {"query": "height restricted when road width is less than 9 m irrespective of FAR"},
             "road width may also limit height, which the setback table does not state")]),
    (re.compile(r"\bhigh[- ]rise\b", re.I),
     [Action("search_corpus", {"query": "high rise building minimum road width site dimension"},
             "text mentions high-rise buildings")]),
]
_TABLE_REF = re.compile(r"Tables? ((?:\d+(?:, | and )?)+)")


class RulePlanner:
    name = "rule"

    def __init__(self, ent: Dict, ev: EvidenceBundle):
        self.ent, self.ev = ent, ev
        self.queue: List[Action] = []
        self.fields_read = False
        self.first_search_done = False
        self.searched_topics: Set[str] = set()
        self.by_id_tried: Set[str] = set()
        self.looked_up = False
        self.topics = topics_for(ent)
        self.strategy = "initial"

    def observe(self, new_passages):
        """Modifier step: derive follow-up actions from the text just read."""
        for p in new_passages:
            for rx, acts in _HINTS:
                if rx.search(p.text):
                    for a in acts:
                        self._enqueue(a)
            for m in _TABLE_REF.finditer(p.text):
                if p.source_doc == B:
                    for n in re.findall(r"\d+", m.group(1)):
                        cid = f"{B}/Table-{n}"
                        if cid not in self.ev.passages and n in ("4", "5", "6"):
                            self._enqueue(Action("get_clause", {"clause_id": cid}, f"{p.clause_id} points to Table {n}"))

    def _enqueue(self, a: Action):
        if a.tool == "search_corpus" and a.args["query"] in self.ev.queries:
            return
        if any(q.tool == a.tool and q.args == a.args for q in self.queue):
            return
        self.queue.append(a)

    def missing(self) -> Dict[str, List[str]]:
        return {t: [i for i in ids if i not in self.ev.passages and i not in self.ev.unresolved]
                for t, ids in self.topics.items() if any(i not in self.ev.passages and i not in self.ev.unresolved for i in ids)}

    def retarget(self, missing_ids: List[str]):
        """Verification failed: switch strategy. Look the missing clauses up by identifier."""
        self.strategy = "targeted"
        self.ev.unresolved = [u for u in self.ev.unresolved if u not in missing_ids]
        for cid in missing_ids:
            self.by_id_tried.discard(cid)
            self._enqueue(Action("get_clause", {"clause_id": cid}, "verification failed: fetch the clause by identifier"))

    def next_action(self) -> Action:
        if not self.fields_read:
            self.fields_read = True
            return Action("get_request_fields", {}, "read the request's own fields")
        if self.queue:
            return self.queue.pop(0)
        if not self.first_search_done:
            self.first_search_done = True
            self.searched_topics.add("setbacks")
            return Action("search_corpus", {"query": topic_query("setbacks", self.ent)},
                          "retrieve the provision that appears to apply")
        gaps = self.missing()
        for topic, ids in gaps.items():
            if topic not in self.searched_topics:
                self.searched_topics.add(topic)
                return Action("search_corpus", {"query": topic_query(topic, self.ent)},
                              f"checklist gap: {topic}")
            for cid in ids:
                if cid not in self.by_id_tried:
                    self.by_id_tried.add(cid)
                    return Action("get_clause", {"clause_id": cid}, f"still missing after search: fetch {cid} by identifier")
        if not self.looked_up and f"{B}/Table-6" in self.ev.passages and self.ent.get("area_class"):
            self.looked_up = True
            return Action("lookup_table", {"table": "bylaw_far_cov", "area": self.ent["area_class"],
                                           "plot": self.ent.get("plot_area_sqm") or self.ent["plot_width_m"] * self.ent["plot_depth_m"],
                                           "road": self.ent["road_width_m"]}, "exact row for the FAR check")
        return Action("finish", {}, "checklist covered or unresolved")


class LLMPlanner:
    """Model proposes the next action; anything invalid falls back to the rule planner."""
    name = "llm"
    ALLOWED = {"get_request_fields", "search_corpus", "get_clause", "lookup_table", "finish"}

    def __init__(self, base: RulePlanner, llm, prompt_dir: Path, rt):
        self.base, self.llm, self.rt = base, llm, rt
        self.template = (prompt_dir / "planner.txt").read_text(encoding="utf-8")
        self.ent, self.ev = base.ent, base.ev

    def observe(self, new):
        self.base.observe(new)

    def retarget(self, ids):
        self.base.retarget(ids)

    def next_action(self) -> Action:
        default = self.base.next_action()          # computed first so state advances consistently
        state = {"retrieved": sorted(self.ev.passages), "queries": self.ev.queries,
                 "missing_by_topic": self.base.missing(), "suggested_by_checklist": {"tool": default.tool, "args": default.args}}
        prompt = self.template.replace("{{STATE}}", json.dumps(state))
        try:
            r = self.llm.complete([{"role": "system", "content": prompt}], "planner")
            self.rt.cost.record("planner", "auditor", r.model, r.prompt_tokens, r.completion_tokens, r.estimated)
            data = json.loads(re.search(r"\{.*\}", r.text, re.S).group(0))
            tool, args = data.get("tool"), data.get("args") or {}
            if tool in self.ALLOWED and isinstance(args, dict):
                if tool == "finish" and (self.base.missing() or self.base.queue):
                    raise ValueError("premature finish")
                if tool == "search_corpus" and not isinstance(args.get("query"), str):
                    raise ValueError("bad query")
                if tool == "get_clause" and not isinstance(args.get("clause_id"), str):
                    raise ValueError("bad clause id")
                if tool == "lookup_table":
                    raise ValueError("lookup_table args are computed by the checklist")
                if tool == "search_corpus" and len(args["query"]) > 300:
                    raise ValueError("query too long")
                self.rt.emit("auditor", "planner", "llm_action", 0, tool=tool, args=args)
                if tool != default.tool or args != default.args:
                    # keep the default queued so the checklist is never skipped
                    self.base.queue.insert(0, default)
                return Action(tool, args, "chosen by the model")
        except Exception as e:  # unparseable, unsafe or premature: use the checklist action
            self.rt.emit("auditor", "planner", "fallback_to_rule", 0, error=str(e)[:120])
        return default


class SinglePassPlanner(RulePlanner):
    """Baseline for the L3 'deliberate change': read the request, run ONE search for the setback provision, stop.
    No modifier step, no checklist, no lookup by id. Use with AGENT_VERIFY_RETRIES=0 to measure what the agent loop adds."""
    name = "single"

    def observe(self, new_passages):
        return

    def next_action(self) -> Action:
        if not self.fields_read:
            self.fields_read = True
            return Action("get_request_fields", {}, "read the request's own fields")
        if not self.first_search_done:
            self.first_search_done = True
            return Action("search_corpus", {"query": topic_query("setbacks", self.ent)}, "single retrieval pass")
        return Action("finish", {}, "single pass done")


def make_planner(settings, ent, ev, llm, rt):
    if settings.planner == "single":
        return SinglePassPlanner(ent, ev)
    base = RulePlanner(ent, ev)
    if settings.planner == "llm":
        return LLMPlanner(base, llm, Path(__file__).parent / "prompts" / settings.prompt_version, rt)
    return base
