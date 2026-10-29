
import hashlib
import re
from pathlib import Path

import chromadb
from pypdf import PdfReader
from sentence_transformers import SentenceTransformer


ROOT = Path(__file__).resolve().parent.parent
CORPUS_DIR = ROOT / "corpus"
DB_DIR = ROOT / "chroma_db"

COLLECTION_NAME = "building_regulations"
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 150


def split_text(text: str) -> list[str]:
    """Split extracted text into overlapping character chunks."""
    text = re.sub(r"\s+", " ", text).strip()

    if not text:
        return []

    chunks = []
    start = 0

    while start < len(text):
        end = min(start + CHUNK_SIZE, len(text))
        chunk = text[start:end].strip()

        if chunk:
            chunks.append(chunk)

        if end == len(text):
            break

        start = end - CHUNK_OVERLAP

    return chunks


def build_index() -> None:
    if not CORPUS_DIR.exists():
        raise FileNotFoundError(f"Corpus folder not found: {CORPUS_DIR}")

    pdf_files = sorted(CORPUS_DIR.glob("*.pdf"))

    if not pdf_files:
        raise FileNotFoundError(f"No PDFs found in {CORPUS_DIR}")

    print("Loading embedding model...")
    model = SentenceTransformer(EMBEDDING_MODEL)

    client = chromadb.PersistentClient(path=str(DB_DIR))
    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )

    # Clear the previous index so rerunning this script
    # rebuilds it from the current PDFs without duplicates.
    client.delete_collection(COLLECTION_NAME)
    collection = client.create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )

    documents = []
    metadatas = []
    ids = []
    skipped_pages = 0

    for pdf_path in pdf_files:
        print(f"\nReading: {pdf_path.name}")
        reader = PdfReader(str(pdf_path))

        for page_number, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""

            if not text.strip():
                skipped_pages += 1
                print(f"  Skipping blank/unreadable page {page_number}")
                continue

            for chunk_number, chunk in enumerate(split_text(text)):
                chunk_id = hashlib.sha256(
                    f"{pdf_path.name}:{page_number}:{chunk_number}".encode()
                ).hexdigest()

                documents.append(chunk)
                ids.append(chunk_id)
                metadatas.append(
                    {
                        "source": pdf_path.name,
                        "page": page_number,
                        "chunk_index": chunk_number,
                    }
                )

    if not documents:
        raise ValueError(
            "No text chunks were extracted. Check whether the PDFs are scanned."
        )

    print(f"\nEmbedding {len(documents)} chunks...")

    batch_size = 64

    for start in range(0, len(documents), batch_size):
        end = start + batch_size
        batch_docs = documents[start:end]

        embeddings = model.encode(
            batch_docs,
            normalize_embeddings=True,
        ).tolist()

        collection.add(
            ids=ids[start:end],
            documents=batch_docs,
            metadatas=metadatas[start:end],
            embeddings=embeddings,
        )

        print(f"Indexed {min(end, len(documents))}/{len(documents)} chunks")

    print("\nIndex build complete!")
    print(f"PDF files processed: {len(pdf_files)}")
    print(f"Chunks indexed: {collection.count()}")
    print(f"Pages skipped: {skipped_pages}")
    print(f"Database location: {DB_DIR}")


if __name__ == "__main__":
    build_index()
