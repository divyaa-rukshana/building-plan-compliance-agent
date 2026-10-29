
from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer


ROOT = Path(__file__).resolve().parent.parent
DB_DIR = ROOT / "chroma_db"

COLLECTION_NAME = "building_regulations"
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


def search_corpus(query: str, k: int = 5) -> list[dict]:
    """
    Retrieve relevant regulation chunks.

    Returns each chunk's text, source PDF, page number,
    chunk index, and cosine distance.
    """
    if not query or not query.strip():
        raise ValueError("Query cannot be empty.")

    if k < 1:
        raise ValueError("k must be at least 1.")

    if not DB_DIR.exists():
        raise FileNotFoundError(
            "Index not found. Run src/indexing.py first."
        )

    client = chromadb.PersistentClient(path=str(DB_DIR))

    try:
        collection = client.get_collection(COLLECTION_NAME)
    except Exception as exc:
        raise RuntimeError(
            "Regulation collection not found. Rebuild the index first."
        ) from exc

    if collection.count() == 0:
        return []

    model = SentenceTransformer(EMBEDDING_MODEL)
    query_embedding = model.encode(
        query.strip(),
        normalize_embeddings=True,
    ).tolist()

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=min(k, collection.count()),
        include=["documents", "metadatas", "distances"],
    )

    matches = []

    documents = results["documents"][0]
    metadatas = results["metadatas"][0]
    distances = results["distances"][0]

    for document, metadata, distance in zip(
        documents, metadatas, distances
    ):
        matches.append({
            "text": document,
            "source": metadata["source"],
            "page": metadata["page"],
            "chunk_index": metadata["chunk_index"],
            "distance": round(float(distance), 4),
        })

    return matches


if __name__ == "__main__":
    question = input("Enter a building regulation question: ")

    for rank, result in enumerate(search_corpus(question), start=1):
        print(f"\n--- Result {rank} ---")
        print("Source:", result["source"])
        print("PDF page:", result["page"])
        print("Cosine distance:", result["distance"])
        print("Text:", result["text"])
