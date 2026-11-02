from src.agents.planner import topics_for
from src.agents.rules import classify_use, evaluate, lookup_table
from src.agents.schemas import ProposalIn


def P(**kw):
    base = dict(area_class="A", use="residential house", plot_width_m=9, plot_depth_m=12, road_width_m=6, height_m=7.5, storeys=2)
    base.update(kw)
    return ProposalIn(**base)


def chk(rep, cid):
    return next(c for c in rep.checks if c.id == cid)


def test_ex1_matches_evaluation1_reference():
    r = evaluate(P(), "residential", "escalate")
    assert chk(r, "setbacks_bylaws").limit_text == "minimum front 1.50, rear 1.50, left 1.00, right 1.00 m"
    assert chk(r, "far_bylaws").limit_text == "maximum FAR 0.75"
    assert "65%" in chk(r, "coverage_bylaws").limit_text


def test_ex2_road_lowers_far_but_not_coverage():
    r = evaluate(P(plot_width_m=20, plot_depth_m=30), "residential", "escalate")
    assert chk(r, "far_bylaws").limit_text == "maximum FAR 0.75"
    assert "60%" in chk(r, "coverage_bylaws").limit_text          # 9.10.7: coverage ignores road width
    assert "9.10.4" in chk(r, "far_bylaws").detail
    assert lookup_table("bylaw_far_cov", area="A", plot=600, road=6)["far_plot_row"] == 1.0


def test_wider_road_does_not_raise_far():
    r = evaluate(P(plot_width_m=9, plot_depth_m=12, road_width_m=18), "residential", "escalate")
    assert chk(r, "far_bylaws").limit_text == "maximum FAR 0.75"     # 9.10.5


def test_taller_building_uses_higher_of_tables_4_and_5():
    r = evaluate(P(height_m=13, storeys=4), "residential", "escalate")
    assert chk(r, "setbacks_bylaws").limit_text.startswith("minimum front 5.00, rear 5.00, left 5.00, right 5.00")
    assert chk(r, "height_cap_rmp").status == "exceeds_limit"


def test_high_rise_on_narrow_road_flags_both_limits():
    r = evaluate(P(plot_width_m=20, plot_depth_m=30, height_m=16, storeys=5), "residential", "escalate")
    d = chk(r, "high_rise").detail
    assert "12 m" in d and "21 m" in d and chk(r, "high_rise").status == "exceeds_limit"


def test_height_cap_only_for_roads_under_9m():
    assert any(c.id == "height_cap_rmp" for c in evaluate(P(), "residential", "escalate").checks)
    assert not any(c.id == "height_cap_rmp" for c in evaluate(P(road_width_m=9), "residential", "escalate").checks)


def test_exemption_and_missing_input():
    assert evaluate(P(plot_width_m=5, plot_depth_m=8), "residential", "escalate").exemption
    assert evaluate(P(area_class=None), "residential", "escalate").needs_input


def test_classification():
    assert classify_use("residential house") == "residential"
    assert classify_use("retail shop") == "commercial"
    assert classify_use("house with a shop") == "mixed-use"
    assert classify_use("residential house", "shop on the ground floor") == "mixed-use"
    assert classify_use("primary school") == "institutional"
    assert classify_use("helipad") == "unknown"


def test_checklist_covers_every_clause_a_finding_needs():
    """The Researcher's checklist must fetch everything the Assessor will cite."""
    for kw in [{}, dict(height_m=13, storeys=4), dict(plot_width_m=20, plot_depth_m=30, height_m=16, storeys=5),
               dict(dwelling_type="multi", ring=1, plot_width_m=14, plot_depth_m=20),
               dict(plot_width_m=5, plot_depth_m=8), dict(zone="R_MIXED"), dict(road_width_m=20)]:
        p = P(**kw)
        needed = {q.clause_id for c in evaluate(p, "residential", "escalate").checks for q in c.reqs}
        ent = p.model_dump()
        listed = {i for ids in topics_for(ent).values() for i in ids}
        assert needed <= listed, (kw, needed - listed)
