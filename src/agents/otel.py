"""D5: OpenTelemetry tracing for one agent run, exported to Jaeger over OTLP gRPC.

One root span ("agent.run") per run carries run_id, correlation_id and prompt_version.
Every trace event the agents already emit (tool call, query, passages returned, model call,
verification outcome, retry, final route) becomes a child span, so a run can be found in
Jaeger by its run_id. L5: model-call spans carry prompt tokens, completion tokens and cost.

If the OpenTelemetry packages are missing, or OTEL_EXPORTER_OTLP_ENDPOINT is not set,
nothing is exported and nothing breaks: tracing must never change the result of a run.
"""
import json
import logging
import os
import time
from typing import Any, Dict, Optional

from src.telemetry import compute_step_billing_metrics

log = logging.getLogger("agents")

_BASE_KEYS = {"t_ms", "run_id", "correlation_id", "agent", "type", "name", "latency_ms"}
_tracer = None
_provider = None
_setup_done = False


def _setup():
    """Create the tracer once per process. Returns None when tracing is unavailable."""
    global _tracer, _provider, _setup_done
    if _setup_done:
        return _tracer
    _setup_done = True
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider

        resource = Resource.create({"service.name": os.environ.get("OTEL_SERVICE_NAME", "agent-worker")})
        _provider = TracerProvider(resource=resource)
        endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "")
        if endpoint:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
            from opentelemetry.sdk.trace.export import BatchSpanProcessor

            _provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=True)))
        _tracer = _provider.get_tracer("building-plan-agents")
    except Exception as e:      # missing package or bad config: run without tracing
        log.warning(json.dumps({"type": "otel", "name": "tracing_disabled", "error": str(e)[:160]}))
        _tracer = None
    return _tracer


def _attr(value: Any):
    """OpenTelemetry attributes must be str, bool, int or float. Anything else becomes JSON text."""
    if isinstance(value, (str, bool, int, float)):
        return value
    return json.dumps(value, default=str)[:2000]


class RunTrace:
    """Use as:  with RunTrace(run_id, correlation_id, prompt_version) as rt:  run(..., hook=rt.hook); rt.finish(result)"""

    def __init__(self, run_id: Optional[str], correlation_id: Optional[str], prompt_version: str = ""):
        self.run_id = run_id or ""
        self.correlation_id = correlation_id or ""
        self.prompt_version = prompt_version
        self._tracer = _setup()
        self._root = None
        self._ctx = None

    def __enter__(self):
        if self._tracer is not None:
            from opentelemetry import trace
            self._root = self._tracer.start_span("agent.run", attributes={
                "run_id": self.run_id, "correlation_id": self.correlation_id, "prompt_version": self.prompt_version})
            self._ctx = trace.set_span_in_context(self._root)
        return self

    def hook(self, ev: Dict[str, Any]):
        """Pass as hook= to run_proposal. Turns one trace event into one child span."""
        if self._tracer is None or self._root is None:
            return
        try:
            end = time.time_ns()
            start = end - int(float(ev.get("latency_ms", 0) or 0) * 1_000_000)
            attrs = {
                "run_id": self.run_id, "correlation_id": self.correlation_id, "prompt_version": self.prompt_version,
                "agent": ev.get("agent", ""), "event.type": ev.get("type", ""), "event.name": ev.get("name", ""),
                "latency_ms": float(ev.get("latency_ms", 0) or 0),
            }
            for k, v in ev.items():
                if k not in _BASE_KEYS:
                    attrs[k] = _attr(v)
            args = ev.get("args")
            if isinstance(args, dict) and "query" in args:
                attrs["query"] = _attr(args["query"])
            if ev.get("type") == "llm" and "prompt_tokens" in ev:          # L5: cost per step, at the time of the call
                m = compute_step_billing_metrics(int(ev["prompt_tokens"]), int(ev.get("completion_tokens", 0)))
                attrs["cost_usd"] = m["calculated_cost_usd"]
            span = self._tracer.start_span(f"{ev.get('agent', '')}.{ev.get('type', '')}.{ev.get('name', '')}",
                                           context=self._ctx, start_time=start, attributes=attrs)
            span.end(end_time=end)
        except Exception:       # a tracing failure must never break a run
            log.exception("otel hook failed")

    def finish(self, result: Dict[str, Any]):
        """Put the outcome and the per-run totals on the root span. `result` is the dict from to_team_result."""
        if self._root is None:
            return
        try:
            t = result.get("telemetry", {})
            self._root.set_attribute("route", str(result.get("decision", "")))
            self._root.set_attribute("outcome", str(result.get("outcome", "")))
            self._root.set_attribute("verified", bool(result.get("verified", False)))
            self._root.set_attribute("degraded", bool(result.get("degraded", False)))
            self._root.set_attribute("corpus_backend", str(result.get("corpus_backend", "")))
            self._root.set_attribute("tokens.prompt", int(t.get("prompt_tokens", 0)))
            self._root.set_attribute("tokens.completion", int(t.get("completion_tokens", 0)))
            self._root.set_attribute("cost_usd", float(t.get("calculated_cost_usd", 0.0)))
            self._root.set_attribute("steps", int(t.get("steps", 0)))
            self._root.set_attribute("tool_calls", int(t.get("tool_calls", 0)))
        except Exception:
            log.exception("otel finish failed")

    def __exit__(self, exc_type, exc, tb):
        if self._root is not None:
            if exc is not None:
                self._root.record_exception(exc)
            self._root.end()
        if _provider is not None:
            try:
                _provider.force_flush(5000)      # rq forks one process per job: flush before it exits
            except Exception:
                log.exception("otel flush failed")
        return False