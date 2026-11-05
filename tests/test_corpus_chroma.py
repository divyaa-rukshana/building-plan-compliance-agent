"""Mapping logic of the Chroma adapter, against a fake src.retrieval (a real index is not available in CI)."""
from src.agents.corpus_chroma import CANONICAL, RetrievalCorpus


class FakeCollection:
    def get(self, where, include):
        conds = {k: v for c in where["$and"] for k, v in c.items()}
        assert conds["source"] == "bbmp_bylaws_2003.pdf" and conds["page"] == 28           # printed 28 == pdf page 28
        return {"metadatas": [{"chunk_index": 1}, {"chunk_index": 0}],
                "documents": ["shall apply.", "9.10.4 When sites do not face the roads of required width noted against each, then the FAR applicable\nto the corresponding width of roads"]}


class FakeRetrieval:
    def get_collection(self):
        return FakeCollection()

    def search_corpus(self, q, k=5):
        return [{"clause_id": "9.10.4", "text": "t", "source": "bbmp_bylaws_2003.pdf", "page": 28, "chunk_index": 0, "distance": 0.2},
                {"clause_id": None, "text": "u", "source": "bda_zoning_regs_rmp2015.pdf", "page": 28, "chunk_index": 3, "distance": 0.5}]

    def get_clause(self, cid):
        return None if cid == "nope" else {"clause_id": cid, "text": "x", "source": "bda_zoning_regs_rmp2015.pdf", "page": 28, "chunk_index": 0}


def test_canonical_get_joins_the_chunks_of_the_cited_page_in_order():
    p = RetrievalCorpus(FakeRetrieval()).get("BBMP2003/9.10.4")
    assert p.page == 28 and p.source_doc == "BBMP2003" and p.text.endswith("shall apply.") and "9.10.4" in p.text


def test_search_maps_sources_and_pages_to_printed_pages():
    a, b = RetrievalCorpus(FakeRetrieval()).search("q", 2)
    assert a.clause_id == "BBMP2003/9.10.4" and a.page == 28
    assert b.source_doc == "RMP2015" and b.page == 27 and b.clause_id == "RMP2015:p27:c3"        # RMP printed = pdf - 1


def test_unknown_clause_is_none_and_every_canonical_id_has_a_source_page():
    assert RetrievalCorpus(FakeRetrieval()).get("RMP2015/nope") is None
    assert len(CANONICAL) == 23
