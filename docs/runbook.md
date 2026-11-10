# Building Plan Compliance Pre-Check – Member 3 Runbook

## 1. Purpose

This runbook documents the data indexing, retrieval, evaluation, configuration, and feedback components of the Building Plan Compliance Pre-Check system.

## 2. Project Components

- **Indexing:** Extracts text from PDF regulations, chunks the content, generates embeddings, and stores them in ChromaDB.
- **Retrieval:** Uses semantic search to retrieve relevant regulation chunks and clause information.
- **Caching:** Caches the embedding model and Chroma collection to reduce repeated initialization.
- **Rate limiting:** Restricts proposal requests to 10 requests per client IP per 60 seconds using Redis.
- **Evaluation:** Uses 20+ scenarios and records retrieval latency and agent evaluation metrics.
- **Prompt versioning:** Supports v1 and v2 prompt configurations.
- **Feedback:** Stores user feedback through the POST `/feedback` endpoint.

## 3. Regulation Corpus

The indexed corpus includes:

1. BBMP Building Bye-laws, 2003.
2. BBMP Violation Procedure, 2007.
3. BDA Zoning Amendments, February 2015.
4. BDA Revised Master Plan Zoning Regulations, 2015.

## 4. Environment Setup

1. Create and activate the Python virtual environment.
2. Install dependencies:

   `pip install -r requirements.txt`

3. Configure environment variables using `.env.example`.
4. Start the application services using Docker Compose.

## 5. Indexing and Retrieval

The indexing pipeline:
- Extracts text from PDF files.
- Splits text into chunks of 1,000 characters with 150-character overlap.
- Generates embeddings using `sentence-transformers/all-MiniLM-L6-v2`.
- Stores vectors and metadata in the `building_regulations` ChromaDB collection.

The retrieval module provides:
- `search_corpus(query, k=5)`
- `get_clause(clause_id)`
- `extract_clause_id(text)`

The ChromaDB persistent directory is `chroma_db`.

## 6. Evaluation

Run retrieval evaluation:

`python evaluation/evaluate_retrieval.py`

Run agent evaluation:

`python -m src.agents.eval_batch --policy both --backend stub`

The evaluation covers:
- Retrieval results and source metadata.
- Retrieval latency.
- Citation support.
- Ungrounded citation rate.
- Unverified answer rate.
- Agent execution time and tool calls.

The retrieval latency report measures warm-run latency and does not include initial model loading.

Retrieval availability does not establish retrieval accuracy. Relevance-labelled test data is required for metrics such as Hit Rate@5 and MRR@5.

## 7. Prompt Versioning

The project maintains two prompt versions:

- `src/agents/prompts/v1/`
- `src/agents/prompts/v2/`

Each contains `planner.txt` and `summary.txt`.

Set `PROMPT_VERSION` to select the desired version.

## 8. Rate Limiting

The `/proposals` endpoint uses Redis-based rate limiting.

- Maximum: 10 requests per client IP.
- Window: 60 seconds.
- Excess requests receive HTTP 429.
- If Redis is unavailable, the current implementation allows requests to continue.

## 9. Feedback Endpoint

Endpoint: `POST /feedback`

Example request:

```json
{
  "run_id": "test-run-001",
  "satisfactory": true,
  "reason": "Test feedback"
}
```

Feedback is appended to `feedback.log` in JSON Lines format.

## 10. Known Limitations

- TruLens is installed, but judge-based groundedness and context relevance evaluation has not yet been integrated.
- The current LLM provider is a stub; genuine LLM-as-judge metrics require a configured judge model.
- Retrieval latency does not establish retrieval relevance or accuracy.
- Clause extraction should be validated against the original regulation before being treated as exact clause isolation.
- Redis failure results in fail-open rate limiting.

## 11. Troubleshooting

- **Missing Python dependency:** Activate `.venv311` and install requirements.
- **ChromaDB build issues on Windows:** Use a compatible Python environment and required C++ build tools.
- **Redis connection issues:** Verify the Redis service and `REDIS_URL`.
- **Empty retrieval results:** Verify that indexing completed and the expected ChromaDB collection exists.
- **Rate-limit errors:** Wait for the 60-second request window to expire.
- **Evaluation scenario file errors:** Verify the scenario file path and the test runner's expected location.