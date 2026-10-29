# Building Plan Compliance Pre-Check Service (Mini Project 05)

**Course:** UE24AM342AA5 – ML System Design & AgentOps  
**Domain:** Urban Development and Construction (BBMP / BDA Jurisdiction)

**Team Members:**
1. A U Divyaa Rukshana (PES2UG24AM002)
2. Amrithaa D J (PES2UG24AM017)
3. Pragya Chowdary S (PES2UG24AM115)

## 1. Overview
A production multi-agent service that accepts a building proposal description, validates it at the ingestion boundary, retrieves binding municipal bye-law provisions (including road-width and height modifiers stated separately from setback tables), verifies every claim against retrieved clauses, and routes the proposal (`clear-for-submission`, `revise-and-recheck`, or `specialist-review`) with clause-level citations.

## 2. Repository Structure
- `corpus/` – Public municipal regulations (`bbmp_bylaws_2003.pdf`, `bda_zoning_regs_rmp2015.pdf`, `bda_zoning_amendments_feb2015.pdf`)
- `docs/` – System architecture diagram, Evaluation 1 deliverable, and data contracts

## 3. Architecture Summary
- **Ingestion & API:** FastAPI, Pydantic (Validation & Quarantine)
- **Agents & Orchestration:** LangGraph (Researcher + Auditor), Redis (Queue, Cache, Rate Limiting)
- **Indexing & Retrieval:** LangChain, Chroma, `all-MiniLM-L6-v2` (Local Embeddings)
- **Observability:** OpenTelemetry, Jaeger, Prometheus, Grafana
- **Deployment & Testing:** Docker Compose, Locust, Stub LLM Service

## 4. Quickstart & Execution
To spin up the entire containerized service locally (API, Redis queue, agent worker, and stub LLM):

- **Clone & Navigate:** Clone the repository and navigate to the root folder:
  `git clone `  
  `cd building-plan-compliance-agent`

- **Build & Run:** Build and run the containers using Docker Compose:
  `docker compose up --build`

- **Access Documentation:** Open your browser and navigate to the interactive Swagger UI[cite: 2]:  
  `http://localhost:8000/docs`[cite: 2]

## 5. Testing & Evaluation
- **API Endpoints:** Submit test proposals via the `POST /proposals` endpoint using Section 4.1 test cases.
- **Worker Logs:** Monitor the terminal output to watch the LangGraph agent execute ingestion, auditing, and self-verification loops against the ChromaDB vector corpus.
