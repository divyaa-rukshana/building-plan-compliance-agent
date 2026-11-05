"""Deterministic rule engine for the residential case (the `lookup_table` tool and the Assessor's source of numbers).

Each Check says what the limit is AND which clause lines must support it (Req). The Verifier later confirms
those lines exist in the passages the Researcher actually retrieved. Numbers come from here, never from a model.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from . import tables as T
from .schemas import ProposalIn

B, R = "BBMP2003", "RMP2015"
EPS = 1e-6


@dataclass
class Req:
    clause_id: str
    numbers: List[float] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)


@dataclass
class Check:
    id: str
    title: str
    status: str
    proposal_value: str
    limit_text: str
    reqs: List[Req]
    source: str
    detail: str = ""


@dataclass
class ConflictItem:
    quantity: str
    bylaws: str
    rmp: str
    clause_ids: List[str]


@dataclass
class RuleReport:
    checks: List[Check]
    conflicts: List[ConflictItem]
    needs_input: List[str]
    exemption: bool
    out_of_scope: Optional[str]
    derived: Dict


def _nums(*xs):
    return [x for x in xs if x is not None and x != T.INF]


# ----------------------------------------------------------------- bye-laws
def bylaw_setbacks(width, depth, height):
    di = T.band(T.T4_DEPTH, depth, 0)
    wi = T.band(T.T4_WIDTH, width, 0)
    _, front, rear = T.T4_DEPTH[di]
    _, left, right = T.T4_WIDTH[wi]
    sb = {"front": front or 0.0, "rear": rear or 0.0, "left": left or 0.0, "right": right or 0.0}
    dlo, dhi = T.lo_hi(T.T4_DEPTH, di, 0)
    wlo, whi = T.lo_hi(T.T4_WIDTH, wi, 0)
    reqs = [Req(f"{B}/Table-4", _nums(dlo, dhi, front, rear), ["depth"]),
            Req(f"{B}/Table-4", _nums(wlo, whi, left, right), ["width"])]
    if height > 9.5:
        a, u, s = next(r for r in T.T5 if r[0] < height <= r[1])
        sb = {k: max(v, s) for k, v in sb.items()}
        reqs.append(Req(f"{B}/Table-5", _nums(a, u, s), ["height"]))
        reqs.append(Req(f"{B}/Note-3", [], ["higher"]))
    else:
        reqs.append(Req(f"{B}/Note-3", [], ["depth"]))
    return sb, reqs


def bylaw_far_cov(area, plot, road):
    rows = T.T6[area]
    ip, ir = T.band(rows, plot, 0), T.band(rows, road, 3)
    ie = min(ip, ir)
    plo, phi = T.lo_hi(rows, ip, 0)
    rlo, rhi = T.lo_hi(rows, ie, 3)
    cov, far = rows[ip][1], rows[ie][2]
    far_req = Req(f"{B}/Table-6", _nums(rows[ie][1], far, rlo, rhi), [f"Area {area}", "FAR"])
    cov_req = Req(f"{B}/Table-6", _nums(plo, phi, cov), [f"Area {area}", "coverage"])
    return {"coverage": cov, "far": far, "far_plot_row": rows[ip][2], "far_road_row": rows[ir][2],
            "road_lowered_far": ir < ip, "road_wider": ir > ip, "far_req": far_req, "cov_req": cov_req}


# --------------------------------------------------------------------- RMP
def rmp_far_cov(zone, plot, road):
    if zone == "R_MAIN":
        rows = T.RMP_T10
        ip, ir = T.band(rows, plot, 0), T.band(rows, road, 3)
        ie = min(ip, ir)
        rlo, rhi = T.lo_hi(rows, ie, 3)
        plo, phi = T.lo_hi(rows, ip, 0)
        return {"coverage": rows[ip][1], "far": rows[ie][2],
                "far_req": Req(f"{R}/Table-10", _nums(rows[ie][1], rows[ie][2], rlo, rhi), ["FAR"]),
                "cov_req": Req(f"{R}/Table-10", _nums(plo, phi, rows[ip][1]), ["coverage"]),
                "clause": f"{R}/Table-10"}
    rows = T.RMP_T12
    ir = T.band(rows, road, 2)
    rlo, rhi = T.lo_hi(rows, ir, 2)
    return {"coverage": rows[ir][0], "far": rows[ir][1],
            "far_req": Req(f"{R}/Table-12", _nums(rows[ir][0], rows[ir][1], rlo, rhi), ["FAR"]),
            "cov_req": Req(f"{R}/Table-12", _nums(rows[ir][0], rlo, rhi), ["coverage"]),
            "clause": f"{R}/Table-12"}


def rmp_setbacks(width, depth, height, plot):
    if height > 11.5:
        a, u, s = next(r for r in T.RMP_T9 if r[0] < height <= r[1])
        sb = {k: s for k in ("front", "rear", "left", "right")}
        return sb, [Req(f"{R}/Table-9", _nums(a, u, s), ["height"])]
    rows = {}

    def row(x):
        if x <= 6:
            return "le6", [6.0, 1.0]
        if x <= 9:
            return "6to9", [6.0, 9.0, 1.0]
        return "gt9", [9.0, 8.0, 12.0]

    wk, wn = row(width)
    dk, dn = row(depth)
    if wk == "le6":
        l, r_ = 0.0, 1.0
    elif wk == "6to9":
        l = r_ = 1.0
    else:
        l = r_ = width * 0.08
    if dk == "le6":
        fr, re_ = 1.0, 0.0
    elif dk == "6to9":
        fr = re_ = 1.0
    else:
        fr, re_ = depth * 0.12, depth * 0.08
    sb = {"front": fr, "rear": re_, "left": l, "right": r_}
    if plot > 4000:
        sb = {k: max(v, 5.0) for k, v in sb.items()}
    rows[wk] = wn
    rows[dk] = dn
    return sb, [Req(f"{R}/Table-8", n, []) for n in rows.values()]


def rmp_height_cap(road):
    return (11.5, 3) if road < 9.0 else (None, None)


# ----------------------------------------------------------- classification
_COMM = ("shop", "office", "commercial", "retail", "hotel", "showroom", "restaurant", "mall", "warehouse", "godown")
_INST = ("school", "hospital", "college", "temple", "mosque", "church", "clinic", "nursing", "institution", "library")
_RES = ("residential", "house", "home", "villa", "apartment", "flat", "dwelling", "bungalow", "residence")


def classify_use(use: str, notes: str = "") -> str:
    """F3: residential | commercial | mixed-use | institutional | unknown."""
    u = use.lower()
    n = notes.lower()
    res = any(w in u for w in _RES)
    comm = any(w in u for w in _COMM)
    inst = any(w in u for w in _INST)
    if inst:
        return "institutional"
    if res and comm:
        return "mixed-use"
    if comm:
        return "commercial"
    if res:
        # notes can reveal a mixed use ("shop on the ground floor") but never override to compliant
        if any(w in n for w in ("shop", "commercial", "office on", "showroom")):
            return "mixed-use"
        return "residential"
    return "unknown"


def classify_proposal(p: ProposalIn) -> str:
    """Declared land_use wins; notes can only make it MORE cautious (residential -> mixed-use), never less."""
    if p.land_use:
        if p.land_use == "residential" and any(w in p.notes.lower() for w in ("shop", "commercial", "showroom", "office on")):
            return "mixed-use"
        return p.land_use
    return classify_use(p.use, p.notes)


def plot_area_of(p: ProposalIn) -> float:
    return p.plot_area_sqm if p.plot_area_sqm else p.plot_width_m * p.plot_depth_m


def lookup_table(table: str, **k):
    """The `lookup_table` agent tool: exact row lookup, no model arithmetic."""
    if table == "bylaw_far_cov":
        r = bylaw_far_cov(k["area"], k["plot"], k["road"])
        return {k_: v for k_, v in r.items() if not k_.endswith("_req")}
    if table == "bylaw_setbacks":
        sb, _ = bylaw_setbacks(k["width"], k["depth"], k["height"])
        return sb
    if table == "rmp_far_cov":
        r = rmp_far_cov(k["zone"], k["plot"], k["road"])
        return {k_: v for k_, v in r.items() if not k_.endswith("_req")}
    raise ValueError(f"unknown table {table}")


# ---------------------------------------------------------------- evaluate
def _cmp_max(proposed, limit):
    return None if proposed is None else ("within_limit" if proposed <= limit + EPS else "exceeds_limit")


def _cmp_min(proposed, limit):
    return None if proposed is None else ("within_limit" if proposed >= limit - EPS else "exceeds_limit")


def evaluate(p: ProposalIn, category: str, policy: str) -> RuleReport:
    checks: List[Check] = []
    conflicts: List[ConflictItem] = []
    needs: List[str] = []
    if category != "residential":
        return RuleReport([], [], [], False, category, {})
    if p.area_class is None:
        needs.append("area_class (A, B or C from the BDA map, bye-law 9.10.1)")
        return RuleReport([], [], needs, False, None, {})

    plot = plot_area_of(p)
    d: Dict = {"plot_area": round(plot, 2)}

    # road width definition (info)
    checks.append(Check("road_width", "Road width used for the checks", "info", f"{p.road_width_m:g} m",
                        "road width = distance between road boundaries incl. footways and drains (2.70)",
                        [Req(f"{B}/2.70", [], ["road width"])], "bylaws"))

    # exemption (7.2)
    exemption = plot < 50 or p.plot_width_m < 6
    if exemption:
        checks.append(Check("min_plot", "Minimum plot size and width for a detached residential building",
                            "exemption_possible", f"plot {plot:g} sq m, width {p.plot_width_m:g} m",
                            "no plan for plot under 50 sq m or width under 6 m; the Authority may relax in specific cases",
                            [Req(f"{B}/7.2", [50.0, 6.0], [])], "bylaws",
                            "An exemption may apply; a human must decide."))

    # setbacks
    bsb, breqs = bylaw_setbacks(p.plot_width_m, p.plot_depth_m, p.height_m)
    rsb, rreqs = rmp_setbacks(p.plot_width_m, p.plot_depth_m, p.height_m, plot)
    d["bylaw_setbacks"], d["rmp_setbacks"] = bsb, rsb

    def sb_status(req_sb):
        if p.proposed_setbacks_m is None:
            return "info"
        prop = p.proposed_setbacks_m.model_dump()
        return "exceeds_limit" if any(prop[k] < req_sb[k] - EPS for k in req_sb) else "within_limit"

    def sb_text(sb):
        return ", ".join(f"{k} {v:.2f}" for k, v in sb.items())

    prop_sb = "" if p.proposed_setbacks_m is None else sb_text(p.proposed_setbacks_m.model_dump())
    checks.append(Check("setbacks_bylaws", "Setbacks (bye-laws Tables 4/5)", sb_status(bsb), prop_sb,
                        "minimum " + sb_text(bsb) + " m", breqs, "bylaws"))
    checks.append(Check("setbacks_rmp", "Setbacks (RMP 2015 Tables 8/9)", sb_status(rsb), prop_sb,
                        "minimum " + sb_text(rsb) + " m", rreqs, "rmp"))
    if any(abs(bsb[k] - rsb[k]) > 0.005 for k in bsb):
        conflicts.append(ConflictItem("setbacks", sb_text(bsb), sb_text(rsb),
                                      [f"{B}/Table-4", f"{R}/Table-8"]))

    # coverage and FAR
    bl = bylaw_far_cov(p.area_class, plot, p.road_width_m)
    rm = rmp_far_cov(p.zone, plot, p.road_width_m)
    d["bylaw_far_cov"] = {k: v for k, v in bl.items() if not k.endswith("_req")}
    d["rmp_far_cov"] = {k: v for k, v in rm.items() if not k.endswith("_req")}

    prop_far = None if p.proposed_floor_area_sqm is None else p.proposed_floor_area_sqm / plot
    prop_far_txt = "" if prop_far is None else f"FAR {prop_far:.2f} ({p.proposed_floor_area_sqm:g} sq m)"
    prop_cov_txt = "" if p.proposed_coverage_pct is None else f"{p.proposed_coverage_pct:g}%"

    far_reqs = [bl["far_req"]]
    if bl["road_lowered_far"]:
        far_reqs += [Req(f"{B}/9.10.4", [], ["corresponding width"])]
        far_detail = (f"Plot-area row allows FAR {bl['far_plot_row']:.2f}, but a {p.road_width_m:g} m road "
                      f"limits FAR to {bl['far']:.2f} (9.10.4).")
    elif bl["road_wider"]:
        far_reqs += [Req(f"{B}/9.10.5", [], ["wider road"])]
        far_detail = "The road is wider than the row requires; FAR stays at the plot-area limit (9.10.5)."
    else:
        far_detail = "Plot-area row and road-width row agree."
    checks.append(Check("far_bylaws", "FAR (bye-laws Table 6, road width limits)", _cmp_max(prop_far, bl["far"]) or "info",
                        prop_far_txt, f"maximum FAR {bl['far']:.2f}", far_reqs, "bylaws", far_detail))
    checks.append(Check("coverage_bylaws", "Ground coverage (bye-laws Table 6)", _cmp_max(p.proposed_coverage_pct, bl["coverage"]) or "info",
                        prop_cov_txt, f"maximum {bl['coverage']}% (coverage ignores road width, 9.10.7)",
                        [bl["cov_req"], Req(f"{B}/9.10.7", [], ["irrespective"])], "bylaws"))
    checks.append(Check("far_rmp", "FAR (RMP 2015 " + ("Table 10" if p.zone == "R_MAIN" else "Table 12") + ")",
                        _cmp_max(prop_far, rm["far"]) or "info", prop_far_txt, f"maximum FAR {rm['far']:.2f}",
                        [rm["far_req"]], "rmp"))
    checks.append(Check("coverage_rmp", "Ground coverage (RMP 2015)", _cmp_max(p.proposed_coverage_pct, rm["coverage"]) or "info",
                        prop_cov_txt, f"maximum {rm['coverage']}%", [rm["cov_req"]], "rmp"))
    if abs(bl["far"] - rm["far"]) > 0.005:
        conflicts.append(ConflictItem("FAR", f"{bl['far']:.2f}", f"{rm['far']:.2f}", [f"{B}/Table-6", rm["clause"]]))
    if bl["coverage"] != rm["coverage"]:
        conflicts.append(ConflictItem("coverage", f"{bl['coverage']}%", f"{rm['coverage']}%", [f"{B}/Table-6", rm["clause"]]))

    # height
    cap_h, cap_floors = rmp_height_cap(p.road_width_m)
    if cap_h is not None:
        over = p.height_m > cap_h + EPS or p.storeys > cap_floors
        checks.append(Check("height_cap_rmp", "Height cap for a road under 9 m (RMP 2015 4.1.2(ii)(b))",
                            "exceeds_limit" if over else "within_limit",
                            f"{p.height_m:g} m, {p.storeys} storeys", f"maximum 11.5 m or Stilt+GF+2 floors (3 storeys), whichever is less",
                            [Req(f"{R}/4.1.2.ii.b", [9.0, 11.5], [])], "rmp",
                            "Applies irrespective of the FAR permissible." if p.zone == "R_MAIN" else
                            "This clause sits under Residential (Main); check whether it also binds a Residential (Mixed) plot."))
    checks.append(Check("height_bylaws", "Height under the bye-laws", "info", f"{p.height_m:g} m",
                        "no fixed number: height is governed by FAR, coverage, setbacks and street width (15.1)",
                        [Req(f"{B}/15.1", [], ["height"])], "bylaws"))

    # high-rise
    if p.storeys >= 5:
        issues = []
        reqs = [Req(f"{B}/2.46", [], ["high-rise"])]
        if p.road_width_m < 12:
            issues.append(f"road {p.road_width_m:g} m is under 12 m (9.3.3)")
        reqs.append(Req(f"{B}/9.3.3", [12.0], []))
        if min(p.plot_width_m, p.plot_depth_m) < 21:
            issues.append(f"site width or depth under 21 m (9.3.2)")
        reqs.append(Req(f"{B}/9.3.2", [21.0], []))
        checks.append(Check("high_rise", "High-rise building (ground + 4 or more floors)",
                            "exceeds_limit" if issues else "within_limit", f"{p.storeys} storeys",
                            "road at least 12 m and site width/depth at least 21 m", reqs, "bylaws", "; ".join(issues)))

    # apartments (RMP 4.1.2(ii)(c))
    if p.dwelling_type == "multi" and p.zone == "R_MAIN":
        if p.ring is None:
            needs.append("ring (1, 2 or 3) to apply the apartments rule (RMP 4.1.2(ii)(c))")
        else:
            need_plot = 360 if p.ring in (1, 2) else 750
            bad = plot <= need_plot or p.road_width_m <= 9.0
            checks.append(Check("apartments", "Apartments (multi dwelling units) in Residential (Main)",
                                "exceeds_limit" if bad else "within_limit",
                                f"plot {plot:g} sq m, road {p.road_width_m:g} m",
                                f"plot above {need_plot} sq m and road more than 9.0 m",
                                [Req(f"{R}/4.1.2.ii.c", [360.0, 750.0, 9.0], [])], "rmp"))

    d["conflicts_n"] = len(conflicts)
    return RuleReport(checks, conflicts, needs, exemption, None, d)


def effective_status(report: RuleReport, policy: str) -> List[Check]:
    """Apply the conflict policy: which source's checks are authoritative for routing."""
    if policy == "bylaws":
        return [c for c in report.checks if c.source != "rmp" or c.id == "height_cap_rmp" or c.id == "apartments"]
    if policy == "rmp":
        return [c for c in report.checks if c.source != "bylaws" or c.id in ("road_width", "height_bylaws", "min_plot", "high_rise")]
    return report.checks  # escalate / stricter: every check counts
