"""Evaluation 1 (Member 2).

Run from the repo root with the three PDFs in ./corpus :
    pip install pypdf
    python eval1_member2/verify_41.py --corpus corpus

Part A: confirms each passage is on the page we will cite.
Part B: computes the worked examples from the Table 4/5/6 values and asserts
        them, so the numbers we show on Tuesday are checked, not typed.
Exit code is 1 if anything fails.
"""
import argparse
import re
import sys
from pathlib import Path

from pypdf import PdfReader

# ---------------------------------------------------------------- Part A
# (file, pdf_page, printed_label, [regexes that must all match], what it decides)
# BBMP bye-laws: printed page == PDF page.  RMP 2015: printed page == PDF page - 1.
CHECKS = [
    ("bbmp_bylaws_2003.pdf", 7, "p.7", [r"2\.70", r"road width", r"aggregate width"],
     "Definition of road width"),
    ("bbmp_bylaws_2003.pdf", 21, "p.21", [r"9\.2", r"Tables 4, 5 and 6"],
     "9.2 points to Tables 4, 5, 6"),
    ("bbmp_bylaws_2003.pdf", 22, "p.22", [r"TABLE 4", r"UPTO 9\.5"],
     "Table 4 setbacks up to 9.5 m"),
    ("bbmp_bylaws_2003.pdf", 23, "p.23", [r"TABLE 5", r"ABOVE 9\.5"],
     "Table 5 setbacks above 9.5 m"),
    ("bbmp_bylaws_2003.pdf", 24, "p.24", [r"TABLE 6", r"INTENSELY DEVELOPED", r"Road width"],
     "Table 6 coverage and FAR, road width in last column"),
    ("bbmp_bylaws_2003.pdf", 25, "p.25", [r"Note 3", r"depth of the site", r"higher of the set ?backs"],
     "Note 3: which dimension sets which setback; higher of Tables 4 and 5"),
    ("bbmp_bylaws_2003.pdf", 26, "p.26", [r"9\.3\.2", r"9\.3\.3", r"12mts"],
     "High-rise needs site >= 21 m and road >= 12 m"),
    ("bbmp_bylaws_2003.pdf", 27, "p.27", [r"9\.10\.1", r"Intensely developed"],
     "A/B/C areas come from a BDA map"),
    ("bbmp_bylaws_2003.pdf", 28, "p.28", [r"9\.10\.4", r"corresponding width of roads"],
     "Road narrower than the row: FAR of the road row applies"),
    ("bbmp_bylaws_2003.pdf", 29, "p.29", [r"9\.10\.5", r"9\.10\.7", r"irrespective of the width"],
     "Wider road: plot-area limit. Setbacks and coverage ignore road width"),
    ("bbmp_bylaws_2003.pdf", 33, "p.33", [r"15\.1", r"width of the street"],
     "Height is governed by FAR, coverage, setbacks, street width (no number)"),
    ("bbmp_bylaws_2003.pdf", 5, "p.5", [r"2\.46", r"high-rise"],
     "High-rise = ground + 4 or more floors"),
    ("bda_zoning_regs_rmp2015.pdf", 28, "p.27", [r"4\.1\.2", r"Table 10", r"less than 9\.0 m", r"11\.5"],
     "RMP 4.1.2(ii)(b): road < 9 m caps height at 11.5 m or Stilt+GF+2"),
    ("bda_zoning_regs_rmp2015.pdf", 20, "p.19", [r"Table 8", r"Up to 6\.0"],
     "RMP Table 8 setbacks as % of depth/width"),
    ("bda_zoning_regs_rmp2015.pdf", 21, "p.20", [r"Table 9", r"Width of the road"],
     "RMP Table 9 setbacks above 11.5 m; 3.2 road width"),
]


def norm(s):
    return re.sub(r"\s+", " ", s)


def part_a(corpus):
    ok = True
    cache = {}
    print("PART A: passages on the cited pages\n")
    for fname, pg, label, pats, why in CHECKS:
        path = corpus / fname
        if not path.exists():
            print(f"  MISSING FILE {fname}")
            ok = False
            continue
        if fname not in cache:
            cache[fname] = PdfReader(str(path))
        text = norm(cache[fname].pages[pg - 1].extract_text() or "")
        miss = [p for p in pats if not re.search(p, text, re.I)]
        status = "OK  " if not miss else "FAIL"
        ok &= not miss
        print(f"  {status} {fname:30s} {label:6s} {why}" + (f"   missing: {miss}" if miss else ""))
    am = corpus / "bda_zoning_amendments_feb2015.pdf"
    if am.exists():
        n = sum(len((p.extract_text() or "").strip()) for p in PdfReader(str(am)).pages)
        print(f"\n  NOTE amendments PDF text layer = {n} chars"
              + ("  -> scanned, OCR needed before indexing" if n < 200 else ""))
    return ok


# ---------------------------------------------------------------- Part B
# Table 4 (residential). Bounds are "up to" values; None = no setback ("-").
T4_DEPTH = [(6, 1.00, None), (9, 1.00, 1.00), (12, 1.50, 1.50),
            (18, 3.00, 1.50), (24, 4.00, 3.00), (float("inf"), 5.00, 3.50)]  # (upto, front, rear)
T4_WIDTH = [(6, None, 1.00), (9, 1.00, 1.00), (12, 1.50, 1.50),
            (18, 1.50, 3.00), (24, 2.50, 3.50), (float("inf"), 3.00, 4.00)]  # (upto, left, right)
# Table 5: (above, upto, setback all round)
T5 = [(9.5, 12, 4.5), (12, 15, 5.0), (15, 18, 6.0), (18, 21, 7.0), (21, 24, 8.0),
      (24, 27, 9.0), (27, 30, 10.0), (30, 35, 11.0), (35, 40, 12.0), (40, 45, 13.0),
      (45, 50, 14.0), (50, float("inf"), 16.0)]
# Table 6 residential: (plot_upto, coverage_%, far, road_upto)
T6 = {
    "A": [(240, 65, 0.75, 6), (500, 60, 0.75, 9), (750, 60, 1.00, 12), (1000, 60, 1.00, 15), (float("inf"), 60, 1.25, float("inf"))],
    "B": [(240, 65, 1.00, 9), (500, 60, 1.25, 12), (750, 60, 1.25, 15), (1000, 60, 1.50, 18), (float("inf"), 60, 1.75, float("inf"))],
    "C": [(240, 65, 1.00, 9), (500, 60, 1.25, 12), (750, 60, 1.50, 15), (1000, 60, 1.50, 18), (float("inf"), 60, 2.00, float("inf"))],
}


def band(rows, value, idx):
    for i, r in enumerate(rows):
        if value <= r[idx]:
            return i
    return len(rows) - 1


def assess(area, width, depth, road, height, storeys=2):
    plot = width * depth
    _, front, rear = T4_DEPTH[band(T4_DEPTH, depth, 0)]
    _, left, right = T4_WIDTH[band(T4_WIDTH, width, 0)]
    sb = {"front": front or 0, "rear": rear or 0, "left": left or 0, "right": right or 0}
    if height > 9.5:  # Note 3(c): higher of Tables 4 and 5
        t5 = next(s for a, u, s in T5 if a < height <= u)
        sb = {k: max(v, t5) for k, v in sb.items()}
    rows = T6[area]
    i_plot = band(rows, plot, 0)
    i_road = band(rows, road, 3)
    far = rows[min(i_plot, i_road)][2]          # 9.10.4 / 9.10.5: the lower row governs
    cov = rows[i_plot][1]                       # 9.10.7: coverage ignores road width
    out = {"plot_area": plot, "setbacks": sb, "coverage_pct": cov, "far": far,
           "max_floor_area": round(far * plot, 2),
           "far_plot_row": rows[i_plot][2], "far_road_row": rows[i_road][2]}
    # 2.46: high-rise = ground + 4 or more floors (5+ storeys). 9.3.2 / 9.3.3 then apply.
    out["high_rise_issue"] = None
    if storeys >= 5:
        issues = []
        if road < 12:
            issues.append("road < 12 m (9.3.3)")
        if min(width, depth) < 21:
            issues.append("site dimension < 21 m (9.3.2)")
        out["high_rise_issue"] = issues or None
    # RMP 2015 4.1.2(ii)(b): road < 9 m caps height at 11.5 m (or Stilt+GF+2)
    cap = 11.5 if road < 9.0 else None
    out["rmp_height_cap_m"] = cap
    out["exceeds_rmp_height_cap"] = bool(cap and height > cap)
    return out


CASES = [
    # id, args, expected subset
    ("EX1", dict(area="A", width=9, depth=12, road=6, height=7.5),
     {"plot_area": 108, "coverage_pct": 65, "far": 0.75,
      "setbacks": {"front": 1.5, "rear": 1.5, "left": 1.0, "right": 1.0}, "rmp_height_cap_m": 11.5}),
    ("EX2", dict(area="A", width=20, depth=30, road=6, height=7.5),
     {"plot_area": 600, "coverage_pct": 60, "far": 0.75, "far_plot_row": 1.00, "far_road_row": 0.75,
      "max_floor_area": 450.0}),
    ("EX3_height_over_9.5", dict(area="A", width=9, depth=12, road=6, height=13.0, storeys=4),
     {"setbacks": {"front": 5.0, "rear": 5.0, "left": 5.0, "right": 5.0},
      "high_rise_issue": None, "exceeds_rmp_height_cap": True}),
    ("EX4_G+4_on_narrow_road", dict(area="A", width=20, depth=30, road=6, height=16.0, storeys=5),
     {"high_rise_issue": ["road < 12 m (9.3.3)", "site dimension < 21 m (9.3.2)"], "exceeds_rmp_height_cap": True,
      "setbacks": {"front": 6.0, "rear": 6.0, "left": 6.0, "right": 6.0}}),
]


def part_b():
    ok = True
    print("\nPART B: worked examples computed from the tables\n")
    for cid, args, exp in CASES:
        got = assess(**args)
        bad = {k: (v, got.get(k)) for k, v in exp.items() if got.get(k) != v}
        ok &= not bad
        print(f"  {'OK  ' if not bad else 'FAIL'} {cid}: {args}")
        print(f"        -> {got}")
        if bad:
            print(f"        expected vs got: {bad}")
    return ok


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default="corpus")
    a = ap.parse_args()
    a_ok = part_a(Path(a.corpus))
    b_ok = part_b()
    print("\nRESULT:", "ALL CHECKS PASSED" if a_ok and b_ok else "FAILURES ABOVE")
    sys.exit(0 if a_ok and b_ok else 1)
