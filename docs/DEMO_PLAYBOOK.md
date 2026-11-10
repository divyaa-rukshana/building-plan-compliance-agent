# Demo playbook: Member 2's items

Start the stack once: `docker compose up -d --build --scale agent-worker=3`. Use `CONFLICT_POLICY=stricter` in `.env` (then `docker compose up -d`) to show the clear and revise routes; the default `escalate` shows the conflict escalation. Examples below use `<id>` for a run id returned by the API.
Submit a request: `curl -X POST localhost:8000/proposals -H "Content-Type: application/json" -d @docs/sample_proposal.json`, poll: `curl localhost:8000/v1/compliance/status/<id>` (within 500 s). The Streamlit client (`src/client.py`) does both.

| Item | Command | Point at |
|---|---|---|
| 1, 2 Start, valid request, citations | `python scripts/smoke_docker.py --n 6` | 14 PASS lines; then the first run's decision, reason and cited clauses |
| 3 One run traced end to end | `docker compose logs agent-worker \| grep <id>` and `python -m src.agents.cli run ex2 --policy stricter --trace` | each tool call with its query and returned clauses, latency, verification, model call with tokens, final route; every line has `run_id` and `correlation_id` |
| 4 Malformed request, no run started | `curl -X POST localhost:8000/proposals -H "Content-Type: application/json" -d "{\"land_use\":\"residential\",\"plot_width_m\":-1}"`, then `docker compose exec redis redis-cli llen rq:queue:agent_queue` | 422 with the validation messages; queue length unchanged; the record in `quarantined_records.jsonl` |
| 5 A case the corpus cannot answer | `python -m src.agents.eval_batch` scenarios 11 to 13 and 23, 24; or `python -m src.agents.cli run ex2 --scenario missing-clause` | "Outside what this system can answer" / "A finding could not be supported ... Corpus may not cover this case"; no invented finding |
| 6 Self-verification catches an unsupported answer | `python -m src.agents.cli run ex2 --policy stricter --debug tamper_far --trace` | `verification ok=false`, `retarget`, a second `verification ok=true`; the wrong-row FAR is corrected |
| 6 (no recovery, so it escalates) | `python -m src.agents.cli run ex2 --scenario missing-clause` | two verification events, then specialist-review |
| 7 Prompt injection | `curl -X POST localhost:8000/proposals -H "Content-Type: application/json" -d @docs/injection_example.json` and `python -m src.agents.cli run inject --trace` | 422 "Quarantined by the input guardrail" with nothing queued; in the worker `status=blocked`, `steps 0/20`, no tool events |
| 8 Provider unavailable (degradation; the breaker is Member 1's) | in `.env` set `LLM_API_BASE=http://127.0.0.1:9`, restart `agent-worker`, submit | `degraded: true`, deterministic findings, specialist-review with "model was unavailable" |
| 10 The 4.1 case | `python -m src.agents.cli run ex2 --policy stricter` and `python -m src.agents.cli run ex1` | Table 4 (setbacks), 9.10.4 (FAR 1.00 lowered to 0.75 by the 6 m road), RMP 4.1.2(ii)(b) (height cap), the conflict table, coverage 60% |
| Loop limits | `AGENT_MAX_STEPS=5 python -m src.agents.cli run ex1` (Windows: `set AGENT_MAX_STEPS=5` first) | "Research did not finish (step limit 5 reached)" |
| Cost | `python -m src.agents.cli cost --n 20` and the `telemetry` block of any result | cost per run, per 100 runs, largest driver (placeholder prices) |
| The agent vs one search | `python -m src.agents.eval_batch`, then again with `AGENT_PLANNER=single` and `AGENT_VERIFY_RETRIES=0` | route accuracy 1.00 against 0.46; clause recall 1.00 against 0.29 |

If a question goes beyond what is built: the agents are residential only, run on the built-in corpus by default, and have not been run against the real Chroma index or a real model provider (`test_example/agent_design.md`, sections 6 and 9).
