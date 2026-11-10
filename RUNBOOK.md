# Operational Runbook: Building Plan Compliance Service

## 1. Failure Mode 1: Redis Queue Stalls / Background Worker Unresponsive
- **Symptom:** API endpoints accept proposals (`202 Accepted`), but compliance run statuses remain indefinitely stuck in 'queued' or 'processing' without updating.
- **Confirmation:** 
  1. Run `docker compose ps` to check container health and inspect logs:
     ```powershell
     docker compose logs -f agent-worker
     ```
  2. Verify if the Redis broker is actively responding to pings:
     ```powershell
     docker compose exec redis redis-cli ping
     ```
- **Recovery Procedure:** Restart the background worker container to re-establish queue bindings:
  ```powershell
  docker compose restart agent-worker
  ```

## 2. Failure Mode 2: ChromaDB Retrieval Connection / Initialization Failure
- **Symptom:** Agent worker throws vector store connection errors or fails to resolve regulatory text chunks during evaluation runs.
- **Confirmation:** Inspect agent-worker logs for vector dimension mismatches or missing persistence volumes:
  ```powershell
  docker compose logs agent-worker
  ```
- **Recovery Procedure:** Rebuild containers and re-run corpus indexing:
  ```powershell
  docker compose up -d --build
  python scripts/index_corpus.py
  ```