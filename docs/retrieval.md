# Retrieval Module

## Corpus
The retrieval system indexes building regulation PDFs:
- BBMP Building Bye-Laws, 2003
- BBMP Violation Procedure, 2007
- BDA Zoning Regulations, RMP 2015
- BDA Zoning Amendments, February 2015

## Indexing
- PDF extraction: pypdf
- Chunk size: 1000 characters
- Chunk overlap: 150 characters
- Embedding model: sentence-transformers/all-MiniLM-L6-v2
- Vector database: ChromaDB
- Similarity metric: Cosine distance
- Persistent storage: chroma_db/

Each chunk stores its source PDF, page number and chunk index.

## Retrieval Functions
- `search_corpus(query, k=5)`: Retrieves the top-k semantically similar chunks.
- `get_clause(clause_id)`: Searches for a clause heading in the indexed corpus.
- `extract_clause_id(text)`: Extracts a clause identifier where possible.

The embedding model and Chroma collection are cached to avoid repeated loading.

## Evaluation
The retrieval evaluation uses 20 predefined queries in `evaluation/scenarios.json`.

The evaluation records:
- Number of retrieved results
- Top result source and page
- Cosine distance
- Query latency
- Top-five retrieved chunks

Initial evaluation:
- Queries tested: 20
- Queries returning five results: 20
- Mean warm-run latency: approximately 16.70 ms

Latency excludes initial model loading and measures query embedding and Chroma retrieval.

Retrieval availability does not represent retrieval accuracy. Manual relevance labels are required before calculating Hit Rate@5 or MRR@5.