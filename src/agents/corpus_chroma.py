"""EXPERIMENTAL adapter: Member 3's Chroma index (src/retrieval.py) behind the agents' corpus interface.

NOT yet tested against a real index (building it needs the embedding model download). Known gap for Member 3:
the agents ask for canonical clause ids (BBMP2003/Table-6, RMP2015/4.1.2.ii.b ...). Chroma chunks are fixed-size slices of raw
PDF text, so a table row is not guaranteed to sit on one line. `get()` therefore returns the whole cited page; verification then
only passes where the page text contains the row. Member 3 should add table-aware chunking and make src/agents/corpus_stub.py's 23
passages the golden target (tests/test_pdf_crosscheck.py already checks them against the PDFs).
"""
import re
from typing import List, Optional

from .corpus_stub import PASSAGES
from .schemas import Passage

# source file -> (document label used in clause ids, printed page = pdf page + offset)
SOURCES = {"bbmp_bylaws_2003.pdf": ("BBMP2003", 0), "bda_zoning_regs_rmp2015.pdf": ("RMP2015", -1)}
_BY_DOC = {doc: (fn, off) for fn, (doc, off) in SOURCES.items()}
CANONICAL = {p.clause_id: (p.source_doc, p.page) for p in PASSAGES}


def _flat(text: str) -> str:
    return re.sub(r"[ \t]+", " ", text).strip()


class RetrievalCorpus:
    def __init__(self, retrieval=None):
        if retrieval is None:
            from src import retrieval as retrieval  # heavy import (chromadb, sentence-transformers): only when selected
        self.r = retrieval

    def search(self, query: str, k: int = 3) -> List[Passage]:
        out = []
        for h in self.r.search_corpus(query, k=k):
            doc, off = SOURCES.get(h["source"], (h["source"], 0))
            cid = h.get("clause_id") or f"{doc}:p{h['page'] + off}:c{h['chunk_index']}"
            out.append(Passage(clause_id=cid if h.get("clause_id") is None else f"{doc}/{h['clause_id']}",
                               page=h["page"] + off, source_doc=doc, text=h["text"], score=round(1 - h["distance"], 4)))
        return out

    def get(self, clause_id: str) -> Optional[Passage]:
        if clause_id in CANONICAL:
            doc, printed = CANONICAL[clause_id]
            fn, off = _BY_DOC[doc]
            col = self.r.get_collection()
            got = col.get(where={"$and": [{"source": fn}, {"page": printed - off}]}, include=["documents", "metadatas"])
            chunks = sorted(zip(got["metadatas"], got["documents"]), key=lambda x: x[0]["chunk_index"])
            if not chunks:
                return None
            return Passage(clause_id=clause_id, page=printed, source_doc=doc, text=_flat("\n".join(d for _, d in chunks)))
        h = self.r.get_clause(clause_id.split("/", 1)[-1])
        if h is None:
            return None
        doc, off = SOURCES.get(h["source"], (h["source"], 0))
        return Passage(clause_id=clause_id, page=h["page"] + off, source_doc=doc, text=h["text"])
