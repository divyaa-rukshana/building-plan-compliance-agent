# Retrieval Module

## Corpus
The retrieval system indexes the building-regulation PDFs stored in `corpus/`, including:
- BBMP Building Bye-Laws, 2003
- BBMP violation procedure, 2007
- BDA Zoning Regulations, RMP 2015
- BDA zoning amendments, February 2015

## Indexing
- PDF text extraction: pypdf
- Chunk size: 1000 characters
- Chunk overlap: 150 characters
- Embedding model: sentence-transformers/all-MiniLM-L6-v2
- Embeddings are normalized before storage.
- Vector database: ChromaDB
- Similarity metric: cosine distance
- Persistent database directory: `chroma_db/`

Each indexed chunk stores its source PDF, PDF page number, and chunk index as metadata.

## Retrieval
`src/retrieval.py` provides:
- `search_corpus(query, k=5)`: retrieves the top-k semantically similar chunks.
- `get_clause(clause_id)`: searches the indexed corpus for a specified clause identifier.
- `extract_clause_id(text)`: attempts to extract a clause identifier from retrieved text.

The embedding model and Chroma collection are cached to avoid repeatedly loading them.

## Evaluation
The retrieval evaluation uses 20 predefined building-regulation queries in `evaluation/scenarios.json`.

`evaluation/evaluate_retrieval.py` records:
- Number of retrieved results
- Top result source and page
- Cosine distance
- Query latency
- Top-five retrieved chunks

The initial run returned five results for all 20 queries. Mean warm-run latency was approximately 16.70 ms (excluding initial model loading).

Retrieval availability does not represent retrieval accuracy. Relevance labels and manual checks are required before calculating Hit Rate@5 or MRR@5.