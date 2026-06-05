from memoryx.context_budget import AdaptiveContextPlanner

def test_planner_selects_modes():
    p = AdaptiveContextPlanner()
    assert p.plan("quick summary").mode == "brief"
    assert p.plan("phase migration architecture patch").mode == "deep"
    assert p.plan("full debug diagnostics raw_fts").mode == "debug"
    assert p.plan("a longer normal question about previous preference").mode == "standard"
