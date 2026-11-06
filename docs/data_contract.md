# Building Proposal Data Contract

Source of truth: `src/schemas.py` (`BuildingProposalRequest`). All requests are JSON submitted to `POST /proposals`. Anything that fails the contract is rejected with HTTP 422 and written to `quarantined_records.jsonl` together with the validation messages; **no job is queued and no agent starts**.

## Request
| Field | Type | Constraint | Meaning |
|---|---|---|---|
| `proposal_id` | string, optional | none | caller's own reference |
| `land_use` | enum | `residential`, `commercial`, `mixed-use`, `institutional` | declared use category |
| `planning_area` | enum | `A`, `B`, `C` (default `A`) | bye-law 9.10.1 area from the BDA map |
| `plot_width_m` | float | `> 0`, `<= 500` | site width |
| `plot_depth_m` | float | `> 0`, `<= 500` | site depth |
| `plot_area_sqm` | float | `> 0`, `<= 250000` | site area |
| `abutting_road_width_m` | float | `> 0`, `<= 100` | width of the road the site faces (bye-law 2.70 definition) |
| `proposed_height_m` | float | `> 0`, `<= 150` | building height |
| `proposed_floors` | integer | `1` to `50` | storeys including the ground floor (G+2 = 3) |
| `proposed_plinth_area_sqm` | float | `> 0` | area covered at plinth level (ground coverage = plinth / plot area) |
| `proposed_total_floor_area_sqm` | float | `> 0` | total floor area (FAR = floor area / plot area) |
| `proposed_setbacks.front_m`, `rear_m`, `left_m`, `right_m` | float | `0` to `50` each | proposed setbacks |
| `notes` | string, optional | at most 1000 characters; screened by `src/security.py` | free text; rejected if it contains a prompt-injection pattern or prohibited language |

**Cross-field rule:** `plot_area_sqm` must be within 15% of `plot_width_m x plot_depth_m`.

## Response (HTTP 202)
`{ "run_id": "run-1a2b3c4d", "correlation_id": "<uuid>", "status": "queued", "metrics": { "submitted_at": "<iso time>" } }`
`run_id` is the queue job id; `correlation_id` is on every log line and trace event of the run.

## Poll
`GET /v1/compliance/status/{run_id}` returns `{ "status": "queued" | "started" | "completed" | "failed" }`, with `"result": {...}` when completed and a generic `"error"` when failed. An unknown id returns 404.
Note: the queue keeps a finished result for 500 seconds by default, after which the same id returns 404; poll within that window or raise `result_ttl` when enqueueing.

## Result (`result`)
| Field | Meaning |
|---|---|
| `status` | `completed` when the job finished; `outcome` says how the run ended (`completed`, `escalated`, `blocked`) |
| `decision` | `clear-for-submission`, `revise-and-recheck` or `specialist-review` |
| `primary_reason` | why, in one sentence |
| `findings[]` | `provision_name`, `is_compliant`, `observed_value`, `required_limit`, `finding_details`, `citations[]` (`clause_id`, `page`, `extracted_text`); also `status`, `verified`, `source` |
| `conflicts[]` | quantities on which the bye-laws and the RMP differ (`quantity`, `bylaws`, `rmp`, `clause_ids`) |
| `verified`, `degraded` | whether every citation was verified; whether the model was unavailable |
| `telemetry` | tokens, cost per step and per run, steps, tool calls, latency per tool |
| `execution_trace[]`, `trace[]` | readable path and the full event list, each with `run_id` and `correlation_id` |
| `corpus_backend`, `prompt_version`, `conflict_policy` | the configuration that produced the result |
| `disclaimer` | a pre-check is not a certification |

## Rejection (HTTP 422)
`{ "detail": "Quarantined: <validation messages>" }` for contract violations; `{ "detail": "Quarantined by the input guardrail: <reason>" }` for prompt-injection or prohibited language in `notes`.
Example: `docs/injection_example.json`.
