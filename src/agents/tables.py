"""Residential table values transcribed from the PDFs (checked by tests/test_pdf_crosscheck.py).
Bye-laws: BBMP Building Bye-Laws 2003 Tables 4, 5, 6.  RMP: BDA RMP 2015 Zoning Regulations Tables 8, 9, 10, 12."""
INF = float("inf")

# Bye-law Table 4 (residential, up to 9.5 m): (upto, front, rear) by depth; (upto, left, right) by width. None = "-"
T4_DEPTH = [(6, 1.00, None), (9, 1.00, 1.00), (12, 1.50, 1.50), (18, 3.00, 1.50), (24, 4.00, 3.00), (INF, 5.00, 3.50)]
T4_WIDTH = [(6, None, 1.00), (9, 1.00, 1.00), (12, 1.50, 1.50), (18, 1.50, 3.00), (24, 2.50, 3.50), (INF, 3.00, 4.00)]
# Bye-law Table 5 (above 9.5 m): (above, upto, setback all round)
T5 = [(9.5, 12, 4.5), (12, 15, 5.0), (15, 18, 6.0), (18, 21, 7.0), (21, 24, 8.0), (24, 27, 9.0),
      (27, 30, 10.0), (30, 35, 11.0), (35, 40, 12.0), (40, 45, 13.0), (45, 50, 14.0), (50, INF, 16.0)]
# Bye-law Table 6 residential: (plot_upto, coverage_pct, far, road_upto)
T6 = {
    "A": [(240, 65, 0.75, 6), (500, 60, 0.75, 9), (750, 60, 1.00, 12), (1000, 60, 1.00, 15), (INF, 60, 1.25, INF)],
    "B": [(240, 65, 1.00, 9), (500, 60, 1.25, 12), (750, 60, 1.25, 15), (1000, 60, 1.50, 18), (INF, 60, 1.75, INF)],
    "C": [(240, 65, 1.00, 9), (500, 60, 1.25, 12), (750, 60, 1.50, 15), (1000, 60, 1.50, 18), (INF, 60, 2.00, INF)],
}
# RMP 2015 Table 10, Residential (Main): (plot_upto, coverage_pct, far, road_upto)
RMP_T10 = [(360, 75, 1.75, 12.0), (1000, 65, 2.25, 18.0), (2000, 60, 2.50, 24.0), (4000, 55, 3.00, 30.0), (20000, 50, 3.25, INF)]
# RMP 2015 Table 12, Residential (Mixed): (coverage_pct, far, road_upto)
RMP_T12 = [(70, 1.75, 12.0), (65, 2.25, 18.0), (60, 2.50, 24.0), (55, 3.00, 30.0), (50, 3.25, INF)]
# RMP 2015 Table 9 (above 11.5 m): (above, upto, setback all round)
RMP_T9 = [(11.5, 15, 5.0), (15, 18, 6.0), (18, 21, 7.0), (21, 24, 8.0), (24, 27, 9.0), (27, 30, 10.0),
          (30, 35, 11.0), (35, 40, 12.0), (40, 45, 13.0), (45, 50, 14.0), (50, INF, 16.0)]


def band(rows, value, idx):
    for i, r in enumerate(rows):
        if value <= r[idx]:
            return i
    return len(rows) - 1


def lo_hi(rows, i, idx):
    """Lower and upper bound of band i (None when open)."""
    lo = rows[i - 1][idx] if i > 0 else None
    hi = rows[i][idx]
    return lo, (None if hi == INF else hi)


def label(lo, hi):
    if lo is None:
        return f"up to {g(hi)}"
    if hi is None:
        return f"over {g(lo)}"
    return f"over {g(lo)} up to {g(hi)}"


def g(x):
    return f"{x:g}"


def f2(x):
    return "-" if x is None else f"{x:.2f}"
