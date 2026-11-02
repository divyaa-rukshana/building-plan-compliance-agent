"""Entry point for Member 1's agent-worker: run_proposal(payload) -> Result dict.

The queue consumer (A4) calls this with the already-validated payload and the run id it issued.
It never raises for a bad run: failures come back as a specialist-review Result (A5: no confident answer).
"""
import logging
import uuid
from typing import Callable, Dict, Optional

from .config import Settings, get_settings
from .corpus_stub import StubCorpus
from .graph import run
from .llm import make_llm
from .runtime import Runtime
from .schemas import Result
from .tools import HttpCorpus

log = logging.getLogger("agents")


def make_corpus(s: Settings):
    """CORPUS_BACKEND: stub (default: the 23 curated, PDF-checked clause passages) | chroma (Member 3's index) | http (CORPUS_API_URL)."""
    if s.corpus_api_url or s.corpus_backend == "http":
        return HttpCorpus(s.corpus_api_url), "http"
    if s.corpus_backend == "chroma":
        from .corpus_chroma import RetrievalCorpus
        return RetrievalCorpus(), "chroma"
    return StubCorpus(), "stub"


def run_proposal(payload: Dict, run_id: Optional[str] = None, *, corpus=None, llm=None,
                 settings: Optional[Settings] = None, hook: Optional[Callable] = None,
                 resilience: Optional[Callable] = None, debug: Optional[str] = None,
                 correlation_id: Optional[str] = None) -> Dict:
    s = settings or get_settings()
    rid = run_id or uuid.uuid4().hex[:12]
    backend = "custom"
    if corpus is None:
        corpus, backend = make_corpus(s)
    elif isinstance(corpus, StubCorpus):
        backend = "stub"
    rt = Runtime(s, corpus, llm or make_llm(s, resilience), rid, hook, debug, correlation_id, backend)
    try:
        out = run(rt, payload)
        out["corpus_backend"] = backend
        return out
    except Exception as e:      # last line of defence: never return a half-run as an answer
        log.exception("run %s crashed", rid)
        rt.emit("worker", "error", "run_crashed", error=str(e)[:200])
        return Result(run_id=rid, status="escalated", route="specialist-review", verified=False,
                      reason=f"The run did not complete ({type(e).__name__}); no result is returned as an answer.",
                      escalation_path=["Run crashed; escalated."], trace=rt.trace, cost=rt.cost.summary(),
                      prompt_version=s.prompt_version, conflict_policy=s.conflict_policy, correlation_id=rt.correlation_id,
                      corpus_backend=backend).model_dump()
