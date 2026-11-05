"""Maps the team's published data contract (src/schemas.py::BuildingProposalRequest, as dumped by the API)
to this package's ProposalIn.  One place to change if the contract changes.

  contract field                    -> agents field                 note
  land_use                          -> land_use (+ use text)        declared category; notes can only make it more cautious
  planning_area                     -> area_class                   bye-law 9.10.1 area A/B/C
  plot_width_m, plot_depth_m        -> same                         setbacks need both
  plot_area_sqm                     -> plot_area_sqm                declared area drives the FAR/coverage rows
  abutting_road_width_m             -> road_width_m
  proposed_height_m                 -> height_m
  proposed_floors                   -> storeys                      ASSUMED to include the ground floor (G+2 = 3)
  proposed_plinth_area_sqm          -> proposed_coverage_pct        plinth / plot area * 100
  proposed_total_floor_area_sqm     -> proposed_floor_area_sqm
  proposed_setbacks.{front,...}_m   -> proposed_setbacks_m.{front,...}
  notes                             -> notes
  zone, ring, dwelling_type         -> same, if the contract ever adds them (defaults: R_MAIN, none, single)
"""
from typing import Any, Dict


def _v(x: Any) -> Any:
    """Enum members (str Enums from model_dump) -> plain values."""
    return getattr(x, "value", x)


def from_team_contract(d: Dict) -> Dict:
    plot_area = d.get("plot_area_sqm") or d["plot_width_m"] * d["plot_depth_m"]
    land_use = _v(d["land_use"])
    sb = d.get("proposed_setbacks") or {}
    out: Dict[str, Any] = {
        "land_use": land_use,
        "use": f"{land_use} building",
        "area_class": _v(d.get("planning_area")),
        "zone": d.get("zone") or "R_MAIN",
        "ring": d.get("ring"),
        "dwelling_type": d.get("dwelling_type") or "single",
        "plot_width_m": d["plot_width_m"],
        "plot_depth_m": d["plot_depth_m"],
        "plot_area_sqm": d.get("plot_area_sqm"),
        "road_width_m": d["abutting_road_width_m"],
        "height_m": d["proposed_height_m"],
        "storeys": d["proposed_floors"],
        "proposed_floor_area_sqm": d.get("proposed_total_floor_area_sqm"),
        "notes": d.get("notes") or "",
    }
    if d.get("proposed_plinth_area_sqm") is not None:
        out["proposed_coverage_pct"] = round(min(100.0, d["proposed_plinth_area_sqm"] / plot_area * 100), 2)
    if sb:
        out["proposed_setbacks_m"] = {"front": sb["front_m"], "rear": sb["rear_m"], "left": sb["left_m"], "right": sb["right_m"]}
    return out
