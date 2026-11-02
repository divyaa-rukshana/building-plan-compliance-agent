# Agent design: Building Plan Compliance Pre-Check

Code: `src/agents/` (graph in `graph.py`), entry point `src/worker.py::run_agent_pipeline`. The behaviour described here is covered by the tests in `tests/` (107 tests; see section 8).

## 1. What the agents do, and do not do
A validated building proposal goes in. Out come one **finding per provision** (limit, proposed value, status, clause citations) and one **route** with a stated reason:
`clear-for-submission`, `revise-and-recheck` or `specialist-review`. The system never certifies a plan: a route is a finding, and a licensed architect or engineer decides.
Scope of this version: **residential** proposals (bye-law Tables 4, 5, 6; RMP 2015 Tables 8, 9, 10, 12, the height cap and the apartments rule). Commercial, mixed-use and institutional proposals are recognised and escalated, not assessed. Parking and fire rules are not checked.

## 2. Topology (LangGraph: three nodes, two agents)
```
                 +---------------------------------------------------------------+
  proposal  ---> | EXTRACTOR (Agent 1: ingestion)                                |
 (from queue)    |  input guardrail -> classify use -> extract entities          |
                 +-------------+-----------------------------+-------------------+
                    blocked    |                             | accepted
                               |                             v
                               |            +-------------------------------------------+
                               |            | AUDITOR (Agent 2)                         |
                               |            |  tool loop, one step per visit            |
                               |            |   get_request_fields / search_corpus /    |
                               |            |   get_clause / lookup_table               |
                               |            |  then: one finding per provision,         |
                               |            |  each with clause citations               |
                               |            +----------------+--------------------------+
                               |                      ^      | EvidenceBundle + findings
                               |        retry once    |      v
                               |        (by clause id)|  +--------------------------------------------+
                               +--------------------> |  | VERIFIER (self-verification layer)         |
                                                      +--| verify every citation against retrieved    |
                                                         | text; retry or escalate; summary; route;   |
                                                         | output filter; result                      |
                                                         +--------------------+-----------------------+
                                                                              v
                                                              result (route, reason, findings, telemetry)
```
| Node | Responsibility | Reads | Produces |
|---|---|---|---|
| **extractor** | `security.screen_input` on `use` and `notes`; classify the use (declared `land_use` wins; notes may only make it *more* cautious); build the entity record; decide whether research is possible | the validated proposal | entities and category; or `blocked` / `skip_research` |
| **auditor** | Bounded loop of tool calls chosen by the planner; then evaluate every applicable limit with the rule engine and attach the clause line that supports each | entities | `EvidenceBundle` (passages, queries, lookups, unresolved ids) and findings |
| **verifier** | Re-check every citation; one retry with a different strategy; model-written summary through the output filter; routing; final output filter | findings and evidence | `Result` |

The hand-off from auditor to verifier is a typed object (`schemas.EvidenceBundle` plus the findings), so a failure in one node never loses what the other produced.

## 3. The auditor is an agent, not a fixed pipeline
Retrieval is a tool the agent chooses to call, not a stage. Tools (`tools.py`) each have a timeout (8 s), are counted against the run's limits, and are traced with their latency:
`get_request_fields()`, `search_corpus(query, k)`, `get_clause(clause_id)`, `lookup_table(table, **keys)` (exact table row, no model arithmetic).

The planner (`planner.py`) decides the next call:
1. read the request's own fields, then run one search for the provision that appears to apply (setbacks);
2. **modifier step:** scan what was just read for hints that another provision modifies it (road width, table references, height) and derive *new queries from that text*, not from the request;
3. close gaps against a per-proposal **checklist** (`topics_for`): a gap triggers a topic search, then lookup by clause id; a clause that cannot be found is recorded as unresolved;
4. stop when the checklist is covered or a limit is hit.

Why it matters (the section 4.1 case, a residential plot on a narrow road): the first search returns the setback table and only 2 to 3 of the 13 to 17 clauses a proposal needs. It misses bye-law 9.10.4 (a narrow road lowers the FAR) and RMP 4.1.2(ii)(b) (a road under 9 m caps height). The loop finds and cites both.
`AGENT_PLANNER=llm` lets a model propose each action; anything invalid, unsafe or premature falls back to the checklist. `AGENT_PLANNER=single` is the one-search baseline used for the L3 comparison.

**Loop limits** (`runtime.check_limits`): 20 steps, 20 tool calls, 60 s wall clock. Reaching any of them ends the run as `specialist-review`. Measured on the reference cases: 11 to 15 steps and 10 to 14 tool calls per run.

## 4. Self-verification (A3)
`verify.verify_findings` accepts a citation only if (1) its clause was retrieved, (2) its quote is a contiguous piece of that clause, and (3) every number and keyword the finding depends on appears in that *same line*. A table row is verified as a row, so a correct number taken from the wrong row fails.
On failure the verifier sends the run back to the auditor **once**, which re-fetches the failing clauses by identifier; if verification fails again the run escalates. An unverified answer is never returned under any route other than `specialist-review`.
Demonstrated by scenarios #23 and #24 (corpus without 9.10.4, or without Table 6) and by a tamper test that injects a wrong-row citation, which is caught and corrected.
Limit: verification proves the numbers sit in the cited line; it cannot tell "up to 6" from "over 6", and it does not prove the legal reasoning.

## 5. Routing (`graph.route`), first match wins
| # | Condition | Route | Run status |
|---|---|---|---|
| 1 | input blocked by the guardrail | specialist-review | blocked |
| 2 | required input missing, or use outside the implemented rule set | specialist-review | escalated |
| 3 | research did not finish (step, tool-call or time limit, repeated tool errors) | specialist-review | escalated |
| 4 | verification failed after the retry | specialist-review | escalated |
| 5 | model unavailable (deterministic findings only, flagged `degraded`) | specialist-review | escalated |
| 6 | an exemption may apply (bye-law 7.2: plot under 50 sq m or width under 6 m) | specialist-review | escalated |
| 7 | bye-laws and RMP disagree and `CONFLICT_POLICY=escalate` (default) | specialist-review | escalated |
| 8 | at least one limit exceeded | revise-and-recheck | completed |
| 9 | setbacks, coverage or floor area not stated, so not checked | revise-and-recheck | completed |
| 10 | every compared limit within bounds **and at least one comparison made** | clear-for-submission | completed |

`security.filter_output_determination_token` is a last guard: a clear route without a verified, checked finding is rewritten to `specialist-review` and traced as `clearance_blocked`.
**Conflict policy.** The bye-laws 2003 and the RMP 2015 give different FAR, coverage and setbacks for almost every residential plot (for a 108 sq m plot in area A: FAR 0.75 against 1.75), and which prevails is not established here. `escalate` (default) refuses to choose, so almost every real proposal goes to specialist-review. `stricter` applies the lower limit of the two; `bylaws` or `rmp` apply one document. Set `CONFLICT_POLICY` in `.env`.

## 6. Fallback paths
| Failure | What happens |
|---|---|
| Malformed or out-of-range request | Rejected and quarantined at the API with the validation messages (field names and reasons); no job is queued |
| Contract drift between API and worker | The worker re-validates with the same contract; a mismatch fails the rq job (status `failed`) instead of producing an answer |
| Injection or prohibited language | Rejected at the API (422, quarantined) and, as defence in depth, blocked again by the extractor with zero tool calls |
| Unknown or unsupported use | The extractor skips research; specialist-review with the reason |
| Tool timeout or error | Recorded; after 3 errors the run ends incomplete and escalates |
| Step, tool-call or time limit | Run ends, evidence kept, specialist-review ("research did not finish") |
| Clause cannot be retrieved | Verification fails, retry by clause id, then specialist-review; never a clear |
| Model provider down or slow (20 s timeout) | Deterministic findings returned, `degraded=true`, specialist-review |
| Model summary contains a determination word or a number not in the findings | Summary rejected, template summary used |
| Unhandled exception in a run | Caught at the worker boundary; a specialist-review result, never a confident answer |
| Corpus backend | `CORPUS_BACKEND` is `stub` (default), `chroma` (Member 3, experimental) or `http`; the result states which one produced it |

Not implemented here: retry with exponential backoff for the model call, and a provider circuit breaker (A5, Member 1). `llm.py` accepts a `resilience` wrapper where a breaker plugs in; the worker does not pass one yet.

## 7. Result
`decision`, `primary_reason`, `findings[]` (provision, is_compliant, observed value, required limit, details, `citations[]` with clause id, printed page and quoted text), `execution_trace[]` (readable), plus `run_id`, `correlation_id`, `verified`, `degraded`, `conflicts[]`, `telemetry`, `limits_used`, `corpus_backend`, `prompt_version`, `conflict_policy` and the full `trace`.
A finding's `status` is one of `within_limit`, `exceeds_limit`, `info` (not compared), `needs_input`, `exemption_possible`.

## 8. Evidence
`python -m src.agents.eval_batch` runs 26 scenarios (`evaluation/agent_scenarios.json`): route accuracy 1.00 under both conflict policies, false-clear rate 0, citation support 1.00.
The one-pass baseline (`AGENT_PLANNER=single AGENT_VERIFY_RETRIES=0`) scores route accuracy 0.46 and required-clause recall 0.29 on the same set (it still never clears what it cannot support: false-clear rate 0).
These numbers use the built-in corpus (23 clause passages checked against the PDFs by `tests/test_pdf_crosscheck.py`) and expected values that I derived by hand from the same tables. A second reader should spot-check them, and they must be re-run on Member 3's index.

## 9. Known limits
Residential only; stub corpus by default; the Chroma adapter is untested against a real index; the model is not needed for correctness (it writes one summary sentence); the injection screens are pattern based; `proposed_floors` is read as storeys including the ground floor.
