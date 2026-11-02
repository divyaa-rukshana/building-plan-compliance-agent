"""A3: verify every finding against the passages that were actually retrieved, before returning anything.

A citation is accepted only if
  1. its clause_id is among the retrieved passages,
  2. its quote is a contiguous piece of that passage's text,
  3. every number the finding depends on appears in that same quote (so a row of a table is checked as a row),
  4. every keyword the finding depends on appears in the quote.
"""
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .rules import Req
from .schemas import Citation, EvidenceBundle

_NUM = re.compile(r"\d+(?:\.\d+)?")


def numbers_in(text: str) -> List[float]:
    return [float(x) for x in _NUM.findall(text)]


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def _units(text: str) -> List[str]:
    """Candidate quote units: each line, then each sentence within a line."""
    out = []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        out.append(line)
        parts = re.split(r"(?<=[.;])\s+(?=[A-Z(‘'])", line)
        if len(parts) > 1:
            out += [p.strip() for p in parts if p.strip()]
    return out


def pick_quote(text: str, numbers: List[float], keywords: List[str]) -> Optional[str]:
    """Shortest unit of the passage that contains every number and keyword, else None."""
    best = None
    for u in _units(text):
        have = numbers_in(u)
        if all(any(abs(n - h) < 1e-9 for h in have) for n in numbers) and \
                all(k.lower() in u.lower() for k in keywords):
            if best is None or len(u) < len(best):
                best = u
    if best is None and not numbers and not keywords:
        best = _norm(text)[:240]
    return best


@dataclass
class Failure:
    finding_id: str
    clause_id: str
    reason: str


@dataclass
class VerifyReport:
    ok: bool
    failures: List[Failure] = field(default_factory=list)
    missing_clause_ids: List[str] = field(default_factory=list)


def build_citations(reqs: List[Req], ev: EvidenceBundle) -> (List[Citation], List[Failure]):
    cites, fails = [], []
    seen = set()
    for q in reqs:
        p = ev.passages.get(q.clause_id)
        if p is None:
            fails.append(Failure("", q.clause_id, "clause was not retrieved"))
            continue
        quote = pick_quote(p.text, q.numbers, q.keywords)
        if quote is None:
            fails.append(Failure("", q.clause_id, f"no line of the retrieved text contains {q.numbers} {q.keywords}"))
            continue
        if (q.clause_id, quote) in seen:
            continue
        seen.add((q.clause_id, quote))
        cites.append(Citation(clause_id=p.clause_id, page=p.page, source_doc=p.source_doc, quote=quote))
    return cites, fails


def verify_findings(findings, reqs_by_finding: Dict[str, List[Req]], ev: EvidenceBundle) -> VerifyReport:
    """Re-check every citation independently of how it was built."""
    fails: List[Failure] = []
    missing = []
    for f in findings:
        reqs = reqs_by_finding.get(f.id, [])
        if not f.citations:
            fails.append(Failure(f.id, "", "finding has no citation"))
        for q in reqs:
            p = ev.passages.get(q.clause_id)
            if p is None:
                fails.append(Failure(f.id, q.clause_id, "clause was not retrieved"))
                missing.append(q.clause_id)
                continue
            cs = [c for c in f.citations if c.clause_id == q.clause_id]
            if not cs:
                fails.append(Failure(f.id, q.clause_id, "required clause not cited"))
                continue
            ok_any = False
            for c in cs:
                inside = _norm(c.quote) in _norm(p.text)
                have = numbers_in(c.quote)
                nums_ok = all(any(abs(n - h) < 1e-9 for h in have) for n in q.numbers)
                kw_ok = all(k.lower() in c.quote.lower() for k in q.keywords)
                if inside and nums_ok and kw_ok:
                    ok_any = True
            if not ok_any:
                fails.append(Failure(f.id, q.clause_id, "cited quote does not support the stated numbers"))
        f.verified = not any(x.finding_id == f.id for x in fails)
    return VerifyReport(not fails, fails, sorted(set(missing)))
