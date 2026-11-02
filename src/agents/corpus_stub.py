"""Hard-coded passages so Member 2 is never blocked (team plan, section 6).

The prose clauses are copied from the PDFs; table passages are generated one row per line
(that is also the chunking Member 3 should aim for: a table row must stay on one line with its column labels).
tests/test_pdf_crosscheck.py checks every passage against the PDF page when the PDFs are available.

page = printed page number. pdf_page offset: BBMP2003 +0, RMP2015 +1.
"""
import math
import re
from typing import Dict, List, Optional

from .schemas import Passage
from . import tables as T

B, R = "BBMP2003", "RMP2015"


def _t4():
    lines = ["TABLE 4 (Bye-law 9.2) Setbacks in metres, residential buildings up to 9.5 m in height"]
    for i, (hi, fr, re_) in enumerate(T.T4_DEPTH):
        lo, h = T.lo_hi(T.T4_DEPTH, i, 0)
        lines.append(f"Residential | depth {T.label(lo, h)} | front {T.f2(fr)} | rear {T.f2(re_)}")
    for i, (hi, l, r) in enumerate(T.T4_WIDTH):
        lo, h = T.lo_hi(T.T4_WIDTH, i, 0)
        lines.append(f"Residential | width {T.label(lo, h)} | left {T.f2(l)} | right {T.f2(r)}")
    return "\n".join(lines)


def _t5():
    lines = ["TABLE 5 (Bye-law 9.2) Setbacks on all sides for buildings above 9.5 m in height"]
    for a, u, s in T.T5:
        lines.append(f"height above {T.g(a)} up to {T.g(u)} | setback {s:.1f}" if u != T.INF
                     else f"height above {T.g(a)} | setback {s:.1f}")
    return "\n".join(lines)


def _t6():
    lines = ["TABLE 6 (Bye-law 9.2 and 9.10) Coverage and FAR, residential buildings, road width in last column"]
    for area, rows in T.T6.items():
        for i, (pu, cov, far, ru) in enumerate(rows):
            plo, phi = T.lo_hi(rows, i, 0)
            rlo, rhi = T.lo_hi(rows, i, 3)
            lines.append(f"Area {area} | plot {T.label(plo, phi)} | coverage {cov}% | FAR {far:.2f} | road {T.label(rlo, rhi)}")
    return "\n".join(lines)


def _t10():
    lines = ["Table 10: FAR and Ground Coverage in Residential (Main)"]
    for i, (pu, cov, far, ru) in enumerate(T.RMP_T10):
        plo, phi = T.lo_hi(T.RMP_T10, i, 0)
        rlo, rhi = T.lo_hi(T.RMP_T10, i, 3)
        lines.append(f"Residential (Main) | plot {T.label(plo, phi)} | coverage {cov}% | FAR {far:.2f} | road {T.label(rlo, rhi)}")
    return "\n".join(lines)


def _t12():
    lines = ["Table 12: FAR and Ground Coverage in Residential (Mixed) zone up to 20000 sq m"]
    for i, (cov, far, ru) in enumerate(T.RMP_T12):
        rlo, rhi = T.lo_hi(T.RMP_T12, i, 2)
        lines.append(f"Residential (Mixed) | coverage {cov}% | FAR {far:.2f} | road {T.label(rlo, rhi)}")
    return "\n".join(lines)


def _t9():
    lines = ["Table 9: All around setbacks for buildings above 11.5 m height"]
    for a, u, s in T.RMP_T9:
        lines.append(f"height above {T.g(a)} up to {T.g(u)} | setback {s:.1f}" if u != T.INF
                     else f"height above {T.g(a)} | setback {s:.1f}")
    return "\n".join(lines)


_T8 = ("Table 8: Setbacks for building height up to 11.5 m and plot size up to 4000 sq m\n"
       "width/depth up to 6.0 | right 1.0 | left 0 | front 1.0 | rear 0\n"
       "width/depth above 6.0 up to 9.0 | 1.0 m on all sides\n"
       "width/depth above 9.0 | right 8% | left 8% | front 12% | rear 8%")

PASSAGES: List[Passage] = [
    Passage(clause_id=f"{B}/2.46", page=5, source_doc=B, text="‘high-rise building’ means a building with ground floor plus four or more floors above the ground floor."),
    Passage(clause_id=f"{B}/2.70", page=7, source_doc=B, text="‘road width’ means the distance between the boundaries of a road including footways and drains measured at right angles to the centre of the plot. In case of roads having service roads in addition to the main roads, the width of road shall be the aggregate width of service roads and main roads for determining FAR and No. of Floors."),
    Passage(clause_id=f"{B}/7.2", page=19, source_doc=B, text="No Plan shall be sanctioned for a residential detached building on a plot measuring less than 50 sqm. or having width less than 6 metres. In specific cases of sites for housing schemes for EWS, LIG, Slum Clearance and Improvement Schemes as well as reconstruction in case of densely populated areas, and plot sub-divided due to family partitions, the Authority may relax the above conditions."),
    Passage(clause_id=f"{B}/9.2", page=21, source_doc=B, text="Exterior open spaces/ set backs, coverage, floor area ratio, numbers of floors and heights - The set backs required on all the sides of building/s, maximum plot coverage, maximum FAR, maximum number of floors, maximum height of buildings that are permissible for different dimensioned sites and widths of roads are set out in Tables 4, 5 and 6 given below."),
    Passage(clause_id=f"{B}/Table-4", page=22, source_doc=B, text=_t4()),
    Passage(clause_id=f"{B}/Table-5", page=23, source_doc=B, text=_t5()),
    Passage(clause_id=f"{B}/Table-6", page=24, source_doc=B, text=_t6()),
    Passage(clause_id=f"{B}/Note-3", page=25, source_doc=B, text="Note 3: (a) The front and rear set backs shall be with reference to the depth of the site.\n(b) The left and right set backs shall be with reference to the width of the site.\n(c) If the height of a building exceeds 9.5 metres, the set backs to be provided shall be higher of the set backs specified in tables 4 and 5."),
    Passage(clause_id=f"{B}/9.3.2", page=26, source_doc=B, text="Minimum depth or width of a site for high rise buildings shall be 21 mtrs."),
    Passage(clause_id=f"{B}/9.3.3", page=26, source_doc=B, text="Minimum road width facing a high rise building shall be 12mts."),
    Passage(clause_id=f"{B}/9.10.1", page=27, source_doc=B, text="The coverage, and FAR, for different sizes of plots with reference to existing road width as limiting factor are given in the table No.6 for various types of buildings like residential, commercial, public and semi-public, etc. The local planning area of Bangalore City is divided into A, B & C areas by the Bangalore Development Authority for the purpose of regulating building constructions as under:- A: Intensely developed area. B: Moderately developed area."),
    Passage(clause_id=f"{B}/9.10.4", page=28, source_doc=B, text="When sites do not face the roads of required width noted against each, then the FAR applicable to the corresponding width of roads shall apply."),
    Passage(clause_id=f"{B}/9.10.5", page=29, source_doc=B, text="When a site faces wider road than the one prescribed against it, the FAR shall be restricted only to the limit prescribed for the area of that particular site."),
    Passage(clause_id=f"{B}/9.10.7", page=29, source_doc=B, text="The set-backs and coverage shall be determined irrespective of the width of the road."),
    Passage(clause_id=f"{B}/15.1", page=33, source_doc=B, text="The height of the building shall be governed by the limitation of the FAR, coverage, setbacks and the width of the street facing the plot as stipulated in the respective tables."),
    Passage(clause_id=f"{R}/Table-8", page=19, source_doc=R, text=_T8),
    Passage(clause_id=f"{R}/Table-9", page=20, source_doc=R, text=_t9()),
    Passage(clause_id=f"{R}/3.4.iii", page=20, source_doc=R, text="When the site does not face the road of required width noted against each, then the FAR applicable to the corresponding width of the roads shall apply."),
    Passage(clause_id=f"{R}/3.4.iv", page=21, source_doc=R, text="Where a plot faces a wider road than the one prescribed against it, the FAR shall be restricted only to the limit prescribed for the area of the plot."),
    Passage(clause_id=f"{R}/Table-10", page=27, source_doc=R, text=_t10()),
    Passage(clause_id=f"{R}/4.1.2.ii.b", page=27, source_doc=R, text="If the road width is less than 9.0 m, then the maximum height is restricted to 11.5 meters or Stilt +GF+2 floors (whichever is less) irrespective of the FAR permissible"),
    Passage(clause_id=f"{R}/4.1.2.ii.c", page=27, source_doc=R, text="Multi dwelling units (Apartments) shall be allowed only on plot sizes of above 360 sq.m in the I and II Ring and on plots above 750 sq.m in the III Ring. In both cases, the road width shall be more than 9.0m."),
    Passage(clause_id=f"{R}/Table-12", page=28, source_doc=R, text=_t12()),
]

_TOK = re.compile(r"[a-z0-9\.]+")


def _tokens(s: str):
    return [t.strip(".") for t in _TOK.findall(s.lower()) if t.strip(".")]


class StubCorpus:
    """Dev-only corpus. Same interface the real Member 3 service must offer:
        search(query, k) -> list[Passage]      get(clause_id) -> Passage | None
    `exclude` removes clauses to simulate a corpus that cannot answer (demo items 5 and 6)."""

    def __init__(self, exclude: Optional[List[str]] = None):
        ex = set(exclude or [])
        self.passages: Dict[str, Passage] = {p.clause_id: p for p in PASSAGES if p.clause_id not in ex}
        self._docs = {cid: _tokens(p.clause_id + " " + p.text) for cid, p in self.passages.items()}
        n = len(self._docs)
        df: Dict[str, int] = {}
        for toks in self._docs.values():
            for t in set(toks):
                df[t] = df.get(t, 0) + 1
        self._idf = {t: math.log(1 + n / c) for t, c in df.items()}

    def search(self, query: str, k: int = 3) -> List[Passage]:
        q = _tokens(query)
        scored = []
        for cid, toks in self._docs.items():
            if not toks:
                continue
            tf = {}
            for t in toks:
                tf[t] = tf.get(t, 0) + 1
            s = sum(self._idf.get(t, 0) * (1 + math.log(tf[t])) for t in set(q) if t in tf)
            s /= math.sqrt(len(toks))
            if s > 0:
                scored.append((s, cid))
        scored.sort(reverse=True)
        return [self.passages[c].model_copy(update={"score": round(s, 4)}) for s, c in scored[:k]]

    def get(self, clause_id: str) -> Optional[Passage]:
        return self.passages.get(clause_id)
