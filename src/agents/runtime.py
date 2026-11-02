"""Per-run context shared by the graph nodes: limits, trace, cost, path of escalation."""
import time
import uuid
import logging
import json
from typing import Any, Callable, Dict, List, Optional

from .config import Settings
from .cost import CostTracker

log = logging.getLogger("agents")
if not log.handlers:                      # JSON lines on stdout so `docker compose logs agent-worker` shows every step
    import sys
    _h = logging.StreamHandler(sys.stdout)
    _h.setFormatter(logging.Formatter("%(message)s"))
    log.addHandler(_h)
    log.setLevel(logging.INFO)
    log.propagate = False


class LimitExceeded(Exception):
    pass


class Runtime:
    def __init__(self, settings: Settings, corpus, llm, run_id: Optional[str] = None,
                 hook: Optional[Callable[[Dict], None]] = None, debug: Optional[str] = None,
                 correlation_id: Optional[str] = None, corpus_backend: str = ""):
        self.s = settings
        self.corpus = corpus
        self.llm = llm
        self.run_id = run_id or uuid.uuid4().hex[:12]
        self.correlation_id = correlation_id or self.run_id
        self.corpus_backend = corpus_backend
        self.t0 = time.monotonic()
        self.trace: List[Dict[str, Any]] = []
        self.path: List[str] = []
        self.cost = CostTracker(settings.price_prompt_per_1k, settings.price_completion_per_1k)
        self.hook = hook
        self.debug = debug          # test/demo hook only, never reachable from the API
        self.degraded = False
        self.steps = 0
        self.tool_calls = 0

    def elapsed(self) -> float:
        return time.monotonic() - self.t0

    def emit(self, agent: str, type_: str, name: str, latency_ms: float = 0.0, **data):
        ev = {"t_ms": round(self.elapsed() * 1000, 1), "run_id": self.run_id, "correlation_id": self.correlation_id, "agent": agent, "type": type_,
              "name": name, "latency_ms": round(latency_ms, 2), **data}
        self.trace.append(ev)
        log.info(json.dumps(ev, default=str))      # structured log line carrying the correlation id (run_id)
        if self.hook:
            try:
                self.hook(ev)
            except Exception:  # a broken hook must never break a run
                log.exception("trace hook failed")

    def note(self, text: str):
        self.path.append(text)

    def check_limits(self):
        if self.steps >= self.s.max_steps:
            raise LimitExceeded(f"step limit {self.s.max_steps} reached")
        if self.tool_calls >= self.s.max_tool_calls:
            raise LimitExceeded(f"tool-call limit {self.s.max_tool_calls} reached")
        if self.elapsed() >= self.s.max_wall_s:
            raise LimitExceeded(f"wall-clock limit {self.s.max_wall_s:g}s reached")
