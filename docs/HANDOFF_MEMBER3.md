# Handoff to Member 3: what is in place and what to finish

The agents, guardrails, verification, telemetry and a first evaluation set are done and tested on the **built-in corpus**. What is left for you is making them work on **your index** and measuring them properly (L1, L3).

## 1. Run what exists (5 minutes)
```
pip install -r requirements-dev.txt
set CORPUS_DIR=corpus
python -m pytest -q                                        # 107 tests
python -m src.agents.eval_batch                            # 26 scenarios, both conflict policies -> evaluation/agent_report.csv
AGENT_PLANNER=single AGENT_VERIFY_RETRIES=0 python -m src.agents.eval_batch --policy stricter   # one-search baseline (Windows: set the two variables first)
python -m src.agents.cli run ex2 --policy stricter --trace # one run with its full trace
```
Current numbers on the built-in corpus (26 scenarios): route accuracy 1.00 under both policies, false-clear rate 0, false-block rate 0, required-clause recall 1.00, citation support 1.00. One-search baseline: route accuracy 0.46, clause recall 0.29, false-clear rate 0.
**Caveat:** the expected outcomes in `evaluation/agent_scenarios.json` were derived by hand by Member 2 from the same tables the rule engine uses. They need a second reader (spot-check at least 6 against the PDFs) before they count as ground truth.

## 2. The interface you must keep
The agents ask for **canonical clause ids** such as `BBMP2003/Table-6`, `BBMP2003/9.10.4`, `RMP2015/4.1.2.ii.b` (all 23 are in `evaluation/golden_passages.json`, with printed page and text). A corpus backend offers two calls:
`search(query, k) -> [Passage(clause_id, page, source_doc, text, score)]` and `get(clause_id) -> Passage | None`.
`CORPUS_BACKEND` in `.env` selects `stub` (the 23 curated passages, default), `chroma` (`src/agents/corpus_chroma.py`, your `src/retrieval.py`) or `http` (`CORPUS_API_URL`). Every result states which backend produced it (`result.corpus_backend`).

## 3. Your tasks, in order
1. **Table-aware chunking (L1).** This is the part that will make or break the switch. Your current chunks are fixed-size slices of raw page text, so a table row is not guaranteed to sit on one line with its labels, and the verifier checks a finding against **one line** (for example `Area A | plot up to 240 | coverage 65% | FAR 0.75 | road up to 6`). Make your index produce the 23 golden passages, one table row per line, and give each chunk the canonical id. Then `RetrievalCorpus.get()` can return them directly.
   Check yourself against `evaluation/golden_passages.json` (a test comparing your chunks with it is the quickest guide; `tests/test_pdf_crosscheck.py` already compares the golden text with the PDFs).
   `src/agents/corpus_chroma.py` is **untested against a real index** (the embedding model could not be downloaded where it was written). Expect to fix it.
2. **Switch the backend and re-run.** `CORPUS_BACKEND=chroma`, then `python -m src.agents.eval_batch --backend chroma`. Every scenario that fails names a clause your chunks do not yet serve. Aim for the same numbers as the built-in corpus; where verification fails the agent escalates, which is safe but lowers route accuracy.
3. **L3 evaluation proper.** `eval_batch` gives route accuracy, false-clear rate, clause recall and a citation support rate (each citation's quote re-checked against the clause text fetched again from the corpus). You still need, with TruLens or equivalent: context relevance (are the retrieved passages relevant to the query: use the `search_corpus` events in `result.trace`), faithfulness (does the model summary stay within the findings: the summary is the only generated text), groundedness and hallucination rate (state how each is computed; the citation re-check is a starting point, `ungrounded_citation_rate` is its complement).
4. **The deliberate change, before and after (L3).** The baseline switch is ready: before = agent loop, after = `AGENT_PLANNER=single AGENT_VERIFY_RETRIES=0` (or another change you choose). Report all four metrics both ways on your index.
5. **Extend the set.** Add scenarios (keep the file format: proposal in the team contract, expected route per policy, `must_cite`, `supporting_passage`, `why`). Scenarios 23 and 24 show how to test "the corpus cannot answer": `corpus_exclude` removes clauses and the agent must escalate.
6. **Load test (D6)** if it is yours: with the team stub a run costs about 0.8 s (0.5 s is the stub's delay); on three workers 9 queued requests finished in 2.8 to 3.6 s. Those are development numbers; declare the SLO before measuring.

## 3b. Settings you will touch (`.env`)
`CONFLICT_POLICY` (`escalate` default | `stricter` | `bylaws` | `rmp`), `AGENT_PLANNER` (`rule` | `llm` | `single`), `PROMPT_VERSION` (`v1` | `v2`, in `src/agents/prompts/`), `AGENT_MAX_STEPS`, `AGENT_MAX_TOOL_CALLS`, `AGENT_MAX_WALL_S`, `PRICE_*`. For L2, `v1` and `v2` are two prompt variants for the planner and the summary; with the stub model they cannot be compared, so run them on a real provider (leave `LLM_MODEL` unset only while using the stub).

## 4. Known issues to be aware of
- With the default policy, almost every real proposal ends as `specialist-review`, because the bye-laws 2003 and the RMP 2015 disagree on FAR, coverage and setbacks. This is deliberate (see `test_example/agent_design.md`, section 5); evaluate with `stricter` when you want clear and revise routes.
- Residential use only. Commercial, mixed-use and institutional proposals are escalated with no findings.
- `docs/data_contract.md` was out of date and has been regenerated from `src/schemas.py`.
- The Feb 2015 amendments PDF has no text layer; OCR it (tesseract) before indexing it. It does not change the numbers the agents use.
- `prometheus.yml` scrapes `api:8000/metrics`, which the API does not expose; that is a Member 1 item.
