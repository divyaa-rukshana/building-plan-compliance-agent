"""Independent check: every stub passage and table number against the real PDF page.
Set CORPUS_DIR to the folder holding the PDFs (default ./corpus); skipped when absent."""
import os
import re
from pathlib import Path

import pytest

pypdf = pytest.importorskip("pypdf")
from src.agents.corpus_stub import PASSAGES  # noqa: E402

DIR = Path(os.environ.get("CORPUS_DIR", "corpus"))
FILES = {"BBMP2003": ("bbmp_bylaws_2003.pdf", 0), "RMP2015": ("bda_zoning_regs_rmp2015.pdf", 1)}
pytestmark = pytest.mark.skipif(not (DIR / "bbmp_bylaws_2003.pdf").exists(), reason="PDFs not found; set CORPUS_DIR")
_cache = {}


def page_text(doc, printed):
    fn, off = FILES[doc]
    if fn not in _cache:
        _cache[fn] = pypdf.PdfReader(str(DIR / fn))
    return _cache[fn].pages[printed + off - 1].extract_text() or ""


def alnum(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


TABLES = {"Table-4", "Table-5", "Table-6", "Table-8", "Table-9", "Table-10", "Table-12"}


@pytest.mark.parametrize("p", PASSAGES, ids=lambda p: p.clause_id)
def test_passage_is_on_its_cited_page(p):
    page = alnum(page_text(p.source_doc, p.page))
    if p.clause_id.split("/")[1] in TABLES:
        # generated rows: every number in the passage must appear on the page
        nums = set(re.findall(r"\d+(?:\.\d+)?", p.text))
        pagenums = set(re.findall(r"\d+(?:\.\d+)?", page_text(p.source_doc, p.page)))
        missing = {n for n in nums if n not in pagenums and float(n) not in {float(x) for x in pagenums}}
        assert not missing, missing
    else:
        assert alnum(p.text) in page, "prose clause is not a verbatim part of the cited page"
