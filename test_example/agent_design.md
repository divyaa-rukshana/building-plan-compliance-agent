# Agent design (Member 2): two agents, hand-off, tools, limits

## Topology

```
request (validated by api) -> redis queue -> agent-worker
   [Researcher agent]  --EvidenceBundle-->  [Assessor agent]  -> result
   classify, extract,                        findings, verify,
   search loop                               route, escalate
```

| | Researcher | Assessor |
|---|---|---|
| Job | F3 classify and extract entities; F4 decide what to search for and in what order | F5 one finding per provision; A3 verify; F6 route; F7 escalate |
| Tools | `get_request_fields(run_id)`, `search_corpus(query, k)`, `get_clause(clause_id)`, `lookup_table(table, **keys)` | `get_clause(clause_id)` (re-read to verify); no search |
| Output | `EvidenceBundle`: entities, list of passages (`clause_id`, `page`, `text`, `source_doc`), the queries tried | `Result`: findings with citations, route, reason, `verified: true/false`, prompt version |

`search_corpus` and `get_clause` are built by Member 3; `lookup_table` (exact Table 4/5/6 row lookup, so the model never does the arithmetic) and the others are mine. Until the index exists, the hard-coded passages from Member 1 stand in.

## Researcher loop (what makes it an agent, not a pipeline)

1. Extract entities (use, plot width and depth, road width, height, storeys, area A/B/C). If `area_class` is missing, stop and ask for it.
2. Search for the provision that appears to apply (setback table for the plot).
3. **Modifier step:** from each retrieved clause, derive new queries from what it says, not from the request. Examples: Table 6 has a road-width column, so search "FAR when site does not face road width listed"; 9.2 names Tables 4-6 and says nothing on height, so search "height limitation road width".
4. Check coverage against a checklist for the use (setbacks, coverage, FAR, height, road width, high-rise limits, parking). A missing item triggers another search with a different strategy (rephrase, clause-id lookup, other document).
5. Stop when the checklist is covered or a limit is hit.

## Assessor and verification (A3)

For each finding the Assessor states the provision, the proposal value, the limit and the result, and cites a `clause_id` and page. The verifier then checks that every citation resolves to retrieved text and that every number in the finding appears in that text. On failure it asks the Researcher for one more search with a different strategy; if that fails, the run **escalates**. An unverified answer is never returned.

## Routing and escalation

| Route | When |
|---|---|
| clear-for-submission | All checklist items found, verified, and no limit exceeded (never described as "compliant") |
| revise-and-recheck | Verified findings show a limit exceeded and a fix is clear |
| specialist-review | Provisions conflict (bye-laws vs RMP 2015), an exemption may apply (e.g. bye-law 7.2 relaxation), the question is outside the corpus, an input is missing, or verification failed twice |

## Limits and failure handling

- Per run: max 12 agent steps, 15 tool calls, 60 s wall clock (30 s on the stub); each model and tool call has its own timeout.
- Researcher fails or times out: run ends as `specialist-review` with reason `research_incomplete` and whatever evidence was gathered.
- Assessor fails after hand-off: the `EvidenceBundle` is kept; one retry, then `specialist-review`.
- Provider circuit open (Member 1): degrade to deterministic `lookup_table` findings, flagged `degraded`, routed to `specialist-review`.

## Safety (L4), summarised

Free-text notes go through an injection screen and toxicity check before any model sees them; the Assessor's output filter blocks the words "compliant" or "approved" as a determination and forces `verified` and a route to be present.
