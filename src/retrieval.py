
from functools import lru_cache
from pathlib import Path
import re

import chromadb
from sentence_transformers import SentenceTransformer


ROOT = Path(__file__).resolve().parent.parent
DB_DIR = ROOT / "chroma_db"

COLLECTION_NAME = "building_regulations"
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


@lru_cache(maxsize=1)
def get_model():
    """Load the embedding model once and reuse it."""
    return SentenceTransformer(EMBEDDING_MODEL)


@lru_cache(maxsize=1)
def get_collection():
    """Connect to the persistent Chroma collection once."""
    if not DB_DIR.exists():
        raise FileNotFoundError(
            "Index not found. Run src/indexing.py first."
        )

    client = chromadb.PersistentClient(path=str(DB_DIR))

    try:
        return client.get_collection(COLLECTION_NAME)
    except Exception as exc:
        raise RuntimeError(
            "Regulation collection not found. Rebuild the index first."
        ) from exc


def extract_clause_id(text: str):
    """Extract a clause ID when the text explicitly identifies one."""
    patterns = [
        r"\b(?:clause|section|regulation|rule)\s+"
        r"(?:no\.?\s*)?(\d+(?:\.\d+){1,5}(?:_[A-Za-z0-9]+)?)\b",
        r"^\s*(\d+(?:\.\d+){1,5})[.)]?\s+\S",
        r"\b(\d+(?:\.\d+){1,5})\s*[.)]?\s+[A-Z][A-Za-z][A-Za-z /&()\-]{2,}",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
        if match:
            return match.group(1)

    return None


def search_corpus(query: str, k: int = 5) -> list[dict]:
    """
    Retrieve relevant regulation chunks.

    Each result contains text, source, page, chunk index,
    clause ID when identifiable, and cosine distance.
    """
    if not query or not query.strip():
        raise ValueError("Query cannot be empty.")

    if k < 1:
        raise ValueError("k must be at least 1.")

    collection = get_collection()
    total = collection.count()

    if total == 0:
        return []

    model = get_model()
    query_embedding = model.encode(
        query.strip(),
        normalize_embeddings=True,
    ).tolist()

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=min(k, total),
        include=["documents", "metadatas", "distances"],
    )

    matches = []

    for document, metadata, distance in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    ):
        matches.append({
            "clause_id": extract_clause_id(document),
            "text": document,
            "source": metadata["source"],
            "page": metadata["page"],
            "chunk_index": metadata["chunk_index"],
            "distance": round(float(distance), 4),
        })

    return matches


def get_clause(clause_id: str):
    """
    Find an indexed chunk containing the exact clause ID.

    Returns the matching chunk, or None if it cannot be found.
    """
    if not clause_id or not clause_id.strip():
        raise ValueError("Clause ID cannot be empty.")

    clause_id = clause_id.strip()

    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}", clause_id):
        raise ValueError("Invalid clause ID format.")

    collection = get_collection()

    results = collection.get(
        include=["documents", "metadatas"],
    )

    pattern = re.compile(
        r"(?<![A-Za-z0-9_.:-])"
        + re.escape(clause_id)
        + r"(?![A-Za-z0-9_.:-])",
        flags=re.IGNORECASE,
    )

    for document, metadata in zip(
        results["documents"],
        results["metadatas"],
    ):
        if pattern.search(document):
            return {
                "clause_id": clause_id,
                "text": document,
                "source": metadata["source"],
                "page": metadata["page"],
                "chunk_index": metadata["chunk_index"],
            }

    return None


if __name__ == "__main__":
    question = input("Enter a building regulation question: ")

    for rank, result in enumerate(search_corpus(question), start=1):
        print(f"\n--- Result {rank} ---")
        print("Clause ID:", result["clause_id"])
        print("Source:", result["source"])
        print("PDF page:", result["page"])
        print("Cosine distance:", result["distance"])
        print("Text:", result["text"])
