# Telemetry, cost tracking and correlation ids (L5, D5 part)

Quick summary for the evaluation panel. Code: `src/telemetry.py` (prices), `src/agents/runtime.py` (events and logs), `src/agents/cost.py` (per-step tracker), `src/agents/pipeline.py` (result block). Tests: `tests/test_telemetry.py`, `tests/test_queue_integration.py`.

## 1. One id follows a request everywhere
| Id | Created | Travels through | Where to see it |
|---|---|---|---|
| `run_id` (`run-1a2b3c4d`) | `src/api.py` | returned to the caller; becomes the rq **job id**; read by the worker with `get_current_job().id` | API response, `GET /v1/compliance/status/{run_id}` (as `result.run_id`), every trace event, every log line, the result |
| `correlation_id` (uuid) | `src/api.py`, once per request | returned to the caller; passed to the worker as a job argument | API response, every trace event, every log line, `result.correlation_id`, `result.telemetry` |

A direct `run_proposal` call without a correlation id falls back to the run id, so the field is never empty. Tested: `test_submit_queue_worker_status_roundtrip_with_one_correlation_id` (the id the caller received is on every event of the run) and `test_worker_still_blocks_an_injection_that_bypasses_the_api` (an id passed to the job is kept).

## 2. What is recorded for every run
**Trace events** (`result.trace`, also printed as one JSON line each on the `agent-worker` log): `t_ms` since the run started, `run_id`, `correlation_id`, `agent` (`extractor`, `auditor` or `verifier`), `type` (`guard`, `step`, `tool`, `verify`, `llm`, `retry`, `limit`, `result`), `name`, `latency_ms`, plus arguments and outcome: the query, the clause ids returned, whether a clause was found, the verification outcome and its failures, the route.
A run can be reconstructed from its id alone: `docker compose logs agent-worker | grep run-1a2b3c4d` shows every tool call with its query and returned clauses, the verification result, the model call with its token counts, and the final route. The same list is in the result, and `result.execution_trace` is a readable version.
Not in the trace by design: the text of `notes` (it is screened and then dropped), and the prompt text.
`prompt_version`, `conflict_policy` and `corpus_backend` are stored on every result, so a number can always be tied to the configuration that produced it.

## 3. Tokens and cost, per step and per run
Every model call is recorded when it happens (`CostTracker.record`) with the agent, step name, model, prompt tokens, completion tokens and whether the counts were **estimated** (4 characters per token, used only when the provider returns no usage). Provider-reported counts are used when present; the team's stub reports 50 and 10.
Each step is priced by `telemetry.compute_step_billing_metrics`, the single place for prices: `tokens / 1000 x price per 1k`, for prompt and completion. Prices come from `PRICE_PROMPT_PER_1K` and `PRICE_COMPLETION_PER_1K`; the defaults are the team's placeholder rates (0.0015 and 0.0020 per 1k), **not** a real provider's.
`result.telemetry` holds the totals and the per-step list. A real run through the API, the queue, a worker and the team's stub (values copied from that run):
```
"telemetry": { "run_id": "run-82f5d343", "correlation_id": "989b68e5-9d98-4a3c-a47c-54470d9d9c1f", "llm_calls": 1,
  "prompt_tokens": 50, "completion_tokens": 10, "tokens_estimated": false,
  "calculated_cost_usd": 9.5e-05, "cost_per_100_runs_estimate": 0.0095,
  "steps": 11, "tool_calls": 10, "wall_s": 0.843,
  "latency_ms_by_step_name": {"get_request_fields": 8.89, "search_corpus": 32.31, "get_clause": 11.12, "lookup_table": 1.19, "summary": 610.97},
  "cost_by_step": [{"step": "summary", "agent": "verifier", "model": "stub", "prompt_tokens": 50, "completion_tokens": 10,
                    "cost": 9.5e-05, "estimated": false, "latency_ms": 610.97}] }
```
**Cost per 100 runs and the largest driver:** `python -m src.agents.cli cost --n 20`, or the `cost` field of `python -m src.agents.eval_batch`. With the default rule planner the only model call is the summary, so the summary is the largest cost driver by construction (measured: one call per run). With `AGENT_PLANNER=llm` every auditor step adds a call and the planner becomes the driver (expected, not measured). The numbers printed today are placeholders until real prices and a real provider are used.

## 4. Latency and limits
Every tool call and every model call has its own latency in the trace; `latency_ms_by_step_name` sums them per name, `wall_s` is the whole run, and `limits_used` gives steps, tool calls and seconds against their maximums (20, 20, 60 s).
Measured on the running stack (real Redis, the API, three workers, the team's stub, in-process corpus): a run takes 11 to 15 steps and 10 to 14 tool calls; for the run above the five kinds of tool call took about 54 ms in total and the single model call about 611 ms, so **the model call is about three quarters of the run time** (the stub sleeps 0.5 s). Nine requests submitted together finished in 2.8 to 3.6 s on three workers. These are development measurements, not the D6 load test or its SLO.

## 5. What is not monitored (say this before being asked)
- No Prometheus metrics come from the agents. `prometheus.yml` scrapes `api:8000/metrics`, which the API does not expose yet (Member 1).
- No OpenTelemetry spans or Jaeger traces. `run_proposal(..., hook=fn)` calls `fn(event)` for every trace event, which is where spans can be created; it is not connected.
- No dashboard, alert or retry-rate figure.
- Prices are placeholders; with the stub, token counts are the stub's fixed 50 and 10.
- The quarantine log is a file inside the API container and is lost when the container is removed.
- Logs are plain JSON lines on stdout, with no shipping or retention.

## 6. How to show it
```
python scripts/smoke_docker.py --n 6                       # runs 6 requests and checks ids, telemetry and logs
docker compose logs agent-worker | grep <run_id>           # the whole run from its id
python -m src.agents.cli cost --n 20                       # cost per 100 runs, largest driver
```
