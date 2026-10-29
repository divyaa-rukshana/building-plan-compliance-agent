# Building Plan Compliance Pre-Check Service

**Mini Project 05 · UE24AM342AA5 – ML System Design & AgentOps**
Domain: Urban Development and Construction (BBMP / BDA jurisdiction)

## Team

| # | Name | SRN |
|---|------|-----|
| 1 | A U Divyaa Rukshana | PES2UG24AM002 |
| 2 | Amrithaa D J | PES2UG24AM017 |
| 3 | Pragya Chowdary S | PES2UG24AM115 |

## Overview

A production multi-agent service that pre-checks a building proposal against municipal bye-laws before it goes for sanction. It:

1. Accepts a building proposal and validates it at the ingestion boundary.
2. Retrieves every binding provision, including road-width and height limits that are stated separately from the setback tables.
3. Verifies each claim against the retrieved clauses.
4. Routes the proposal to one of `clear-for-submission`, `revise-and-recheck` or `specialist-review`, with clause-level citations.

> The system never certifies a plan as compliant. It produces a finding with supporting evidence, and a licensed architect or engineer makes the decision.

## Repository Structure

```text
.
├── corpus/                              # Public regulations (the knowledge base)
│   ├── bbmp_bylaws_2003.pdf
│   ├── bbmp_violation_procedure_2007.pdf
│   ├── bda_zoning_regs_rmp2015.pdf
│   └── bda_zoning_amendments_feb2015.pdf
├── evaluation/
│   └── scenarios.json                   # Evaluation scenarios
├── src/                                 # Service source code
│   ├── api.py                           # FastAPI endpoints
│   ├── schemas.py                       # Request data contract (Pydantic)
│   ├── worker.py                        # Agent worker
│   ├── indexing.py                      # Builds the vector index
│   ├── retrieval.py                     # Corpus search
│   ├── stub_llm.py                      # Fake LLM service for tests
│   └──telemetry.py                      # Tracing and metrics
├── test_example/                        # Section 4.1 reference case
│   ├── agent_design.md
│   ├── passages_41.md
│   ├── verify_41.py
│   └── check_output.txt
├── docker-compose.yml                   # Starts all services
├── dockerfile                           # Container image build
├── requirements.txt                     # Python dependencies
├── .gitignore
└── README.md
```

## Architecture

| Layer | Technologies | Role |
|-------|--------------|------|
| Ingestion and API | FastAPI, Pydantic | Validation and quarantine of requests |
| Agents and orchestration | LangGraph (Researcher + Auditor), Redis | Reasoning loop, job queue, cache, rate limiting |
| Indexing and retrieval | LangChain, Chroma, `all-MiniLM-L6-v2` | Chunking and local embeddings of the corpus |
| Observability | OpenTelemetry, Jaeger, Prometheus, Grafana | Traces, metrics, dashboards |
| Deployment and testing | Docker Compose, Locust, stub LLM service | Containers and load testing |

## Getting Started

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) with Docker Compose
- Git

### 1. Clone the repository

```bash
git clone https://github.com/divyaa-rukshana/building-plan-compliance-agent
cd building-plan-compliance-agent
```

### 2. Configure the environment

```bash
cp .env.example .env
```

Fill in the values in `.env`. No keys or model names are stored in the repository.

### 3. Build and start the services

```bash
docker compose up --build
```

This starts the API, the Redis queue, the agent worker and the stub LLM service.

### 4. Open the API documentation

Go to the interactive Swagger UI at: <http://localhost:8000/docs>

### 5. Stop the services

```bash
docker compose down
```

## Testing and Evaluation

- **Submit a proposal:** use the `POST /proposals` endpoint in the Swagger UI with the section 4.1 test cases.
- **Watch the agent run:** follow the worker logs in the terminal to see the LangGraph agent perform ingestion, auditing and self-verification against the Chroma vector corpus.
