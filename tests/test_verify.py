from src.agents.corpus_stub import StubCorpus
from src.agents.rules import Req
from src.agents.schemas import EvidenceBundle
from src.agents.verify import build_citations, pick_quote


def ev(*ids, exclude=()):
    c = StubCorpus(exclude=list(exclude))
    e = EvidenceBundle()
    for i in ids:
        e.passages[i] = c.get(i)
    return e


def test_quote_is_the_single_table_row():
    t = StubCorpus().get("BBMP2003/Table-6").text
    q = pick_quote(t, [65, 0.75, 6], ["Area A", "FAR"])
    assert q == "Area A | plot up to 240 | coverage 65% | FAR 0.75 | road up to 6"


def test_wrong_row_numbers_do_not_verify():
    t = StubCorpus().get("BBMP2003/Table-6").text
    assert pick_quote(t, [65, 1.00, 6], ["Area A", "FAR"]) is None      # 1.00 and road 6 never share a row
    # Known limit: numbers cannot tell "up to 6" from "over 6", so this finds the 6-9 m row. It is still a real row of
    # the right table, and the finding builder always requests the full row (coverage, FAR and both bounds).
    assert pick_quote(t, [60, 0.75, 6], ["Area A", "FAR"]) == "Area A | plot over 240 up to 500 | coverage 60% | FAR 0.75 | road over 6 up to 9"


def test_missing_clause_fails():
    cites, fails = build_citations([Req("BBMP2003/9.10.4", [], [])], EvidenceBundle())
    assert not cites and fails[0].reason == "clause was not retrieved"


def test_prose_clause_quote():
    e = ev("BBMP2003/9.10.4")
    cites, fails = build_citations([Req("BBMP2003/9.10.4", [], ["corresponding width"])], e)
    assert cites and not fails and cites[0].page == 28
