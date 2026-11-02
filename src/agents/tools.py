"""The Researcher's tools. Retrieval is something the agent chooses to call (A1), never a fixed stage.

  get_request_fields()          the request's own fields
  search_corpus(query, k)       semantic search (Member 3's index; StubCorpus in dev)
  get_clause(clause_id)         exact lookup by identifier
  lookup_table(table, **keys)   exact table row lookup (no model arithmetic)
Every call has a timeout, is counted against the run's limits, and is traced with its latency.
"""
import concurrent.futures as cf
import time
from typing import Dict, List, Optional

import httpx

from . import rules
from .runtime import Runtime
from .schemas import EvidenceBundle, Passage

TOOL_TIMEOUT_S = 8.0
_pool = cf.ThreadPoolExecutor(max_workers=8)


class HttpCorpus:
    """Client for Member 3's retrieval service. ASSUMED contract (agree it with Member 3):
         GET {url}/search?q=...&k=3     -> [{clause_id, page, source_doc, text, score}]
         GET {url}/clause/{clause_id}   -> {clause_id, page, source_doc, text}  or 404"""

    def __init__(self, url: str):
        self.url = url.rstrip("/")

    def search(self, query: str, k: int = 3) -> List[Passage]:
        r = httpx.get(f"{self.url}/search", params={"q": query, "k": k}, timeout=TOOL_TIMEOUT_S)
        r.raise_for_status()
        return [Passage(**x) for x in r.json()]

    def get(self, clause_id: str) -> Optional[Passage]:
        r = httpx.get(f"{self.url}/clause/{clause_id}", timeout=TOOL_TIMEOUT_S)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return Passage(**r.json())


class ToolError(Exception):
    pass


class Tools:
    def __init__(self, rt: Runtime, ev: EvidenceBundle, request: Dict):
        self.rt, self.ev, self.request = rt, ev, request

    def _run(self, name: str, fn, **args):
        self.rt.check_limits()
        self.rt.tool_calls += 1
        self.ev.tool_calls = self.rt.tool_calls
        t = time.perf_counter()
        try:
            res = _pool.submit(fn).result(timeout=TOOL_TIMEOUT_S)
        except cf.TimeoutError:
            self.rt.emit("auditor", "tool", name, (time.perf_counter() - t) * 1000, args=args, error="timeout")
            raise ToolError(f"{name} timed out after {TOOL_TIMEOUT_S:g}s")
        except Exception as e:
            self.rt.emit("auditor", "tool", name, (time.perf_counter() - t) * 1000, args=args, error=str(e)[:200])
            raise ToolError(f"{name} failed: {e}")
        return res, (time.perf_counter() - t) * 1000

    def _add(self, passages: List[Passage]) -> List[Passage]:
        new = []
        for p in passages:
            if p.clause_id not in self.ev.passages:
                self.ev.passages[p.clause_id] = p
                new.append(p)
        return new

    def get_request_fields(self):
        res, ms = self._run("get_request_fields", lambda: dict(self.request))
        self.rt.emit("auditor", "tool", "get_request_fields", ms, args={}, result_keys=sorted(res))
        return res, []

    def search_corpus(self, query: str, k: int = 3):
        res, ms = self._run("search_corpus", lambda: self.rt.corpus.search(query, k), query=query, k=k)
        self.ev.queries.append(query)
        new = self._add(res)
        self.rt.emit("auditor", "tool", "search_corpus", ms, args={"query": query, "k": k},
                     returned=[p.clause_id for p in res], new=[p.clause_id for p in new])
        return res, new

    def get_clause(self, clause_id: str):
        res, ms = self._run("get_clause", lambda: self.rt.corpus.get(clause_id), clause_id=clause_id)
        new = self._add([res]) if res else []
        if res is None and clause_id not in self.ev.unresolved:
            self.ev.unresolved.append(clause_id)
        self.rt.emit("auditor", "tool", "get_clause", ms, args={"clause_id": clause_id}, found=res is not None)
        return res, new

    def lookup_table(self, table: str, **keys):
        res, ms = self._run("lookup_table", lambda: rules.lookup_table(table, **keys), table=table, keys=keys)
        self.ev.lookups.append({"table": table, "keys": keys, "result": res})
        self.rt.emit("auditor", "tool", "lookup_table", ms, args={"table": table, **keys}, result=res)
        return res, []
