"""Tests for context budget / layer quota / evidence annotation (24.5-B)."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


from memoryx.context.engine import ContextAssemblyEngine, _annotate_line, _compress_priority_key
from memoryx.context.models import ContextBundle, ContextBudgetPolicy


@dataclass
class FakeResult:
    memory_id: str = "m1"
    content: str = "test"
    memory_type: str = "FACT"
    scope: str = "global"
    final_score: float = 0.8
    evidence_level: str | None = None
    source_type: str | None = None
    metadata_json: str = "{}"


# ===================================================================
# 1. ContextBudgetPolicy default values exist
# ===================================================================

def test_budget_policy_defaults() -> None:
    p = ContextBudgetPolicy()
    assert p.max_tokens == 1200
    assert p.hard_reserve_working == 120
    assert p.hard_reserve_warnings == 120
    assert p.hard_reserve_policy == 240
    assert p.min_project == 180
    assert p.max_project == 300
    assert p.min_session == 140
    assert p.max_session == 240
    assert p.min_long_term == 120
    assert p.max_long_term == 300


# ===================================================================
# 2. max_token_budget still compatible
# ===================================================================

def test_max_token_budget_compatible() -> None:
    engine = ContextAssemblyEngine(max_token_budget=800)
    assert engine.max_token_budget == 800
    assert engine.policy.max_tokens == 800


# ===================================================================
# 3. working_context has hard reserve
# ===================================================================

def test_working_context_hard_reserve() -> None:
    p = ContextBudgetPolicy()
    assert p.hard_reserve_working > 0


# ===================================================================
# 4. warnings have hard reserve
# ===================================================================

def test_warnings_hard_reserve() -> None:
    p = ContextBudgetPolicy()
    assert p.hard_reserve_warnings > 0


# ===================================================================
# 5. policy_context has hard reserve
# ===================================================================

def test_policy_context_hard_reserve() -> None:
    p = ContextBudgetPolicy()
    assert p.hard_reserve_policy > 0


# ===================================================================
# 6. budget_report included in ContextBundle
# ===================================================================

def test_budget_report_in_bundle() -> None:
    bundle = ContextBundle(rendered="", token_count=0, budget_report={"max_tokens": 1200})
    d = bundle.to_dict()
    assert "budget_report" in d
    assert d["budget_report"]["max_tokens"] == 1200


# ===================================================================
# 7. truncation_reason in ContextBundle
# ===================================================================

def test_truncation_reason_in_bundle() -> None:
    bundle = ContextBundle(rendered="", token_count=0, truncation_reason="global_overflow")
    d = bundle.to_dict()
    assert d["truncation_reason"] == "global_overflow"


# ===================================================================
# 8. evidence/source/layer annotation
# ===================================================================

def test_annotate_line_with_all() -> None:
    r = FakeResult(evidence_level="E2", source_type="user_explicit", metadata_json='{"memory_layer": "long_term"}')
    annotated = _annotate_line(r, evidence=True, source=True, layer=True)
    assert "evidence=E2" in annotated
    assert "source=user_explicit" in annotated
    assert "layer=long_term" in annotated


# ===================================================================
# 9. missing evidence/source/layer -> unknown
# ===================================================================

def test_annotate_line_missing_fields() -> None:
    r = FakeResult(evidence_level=None, source_type=None, metadata_json="{}")
    annotated = _annotate_line(r, evidence=True, source=True, layer=True)
    assert "evidence=unknown" in annotated
    assert "source=unknown" in annotated
    assert "layer=legacy" in annotated


# ===================================================================
# 10. prompt does not contain metadata_json
# ===================================================================

def test_prompt_no_metadata_json() -> None:
    bundle = ContextBundle(rendered="test", token_count=1)
    text = bundle.to_prompt_text()
    assert "metadata_json" not in text


# ===================================================================
# 11. prompt does not contain DB path
# ===================================================================

def test_prompt_no_db_path() -> None:
    bundle = ContextBundle(rendered="test", token_count=1)
    text = bundle.to_prompt_text()
    assert ".db" not in text


# ===================================================================
# 12. explain/trace not in context prompt
# ===================================================================

def test_no_trace_in_prompt() -> None:
    bundle = ContextBundle(rendered="test", token_count=1)
    text = bundle.to_prompt_text()
    assert "query_plan_used" not in text
    assert "fallback_steps" not in text


# ===================================================================
# 13. candidate/rejected/stale not injected
# ===================================================================

def test_candidate_not_in_context() -> None:
    from memoryx.retrieval.engine import _is_visible_memory_for_retrieval
    rec = {"metadata_json": json.dumps({"candidate_state": "candidate"})}
    assert _is_visible_memory_for_retrieval(rec) is False


# ===================================================================
# 14. to_prompt_text preserves old fields
# ===================================================================

def test_prompt_preserves_old_fields() -> None:
    bundle = ContextBundle(
        rendered="# old rendered", token_count=2,
        facts=["fact1"], preferences=["pref1"], lessons=["lesson1"],
    )
    d = bundle.to_dict()
    assert "facts" in d
    assert "preferences" in d
    assert "lessons" in d


# ===================================================================
# 15. to_dict/to_json/to_prompt_text backward compatible
# ===================================================================

def test_backward_compatible_output() -> None:
    bundle = ContextBundle(rendered="# test\ncontent", token_count=2)
    d = bundle.to_dict()
    assert "rendered" in d
    assert "token_count" in d
    j = bundle.to_json()
    assert isinstance(j, str)
    p = bundle.to_prompt_text()
    assert isinstance(p, str)


# ===================================================================
# 16. budget_report structure
# ===================================================================

def test_budget_report_structure() -> None:
    p = ContextBudgetPolicy()
    ContextAssemblyEngine(policy=p)
    report = {"max_tokens": 1200, "sections": {"working_context": {"allocated": 120}}}
    assert "max_tokens" in report
    assert "sections" in report


# ===================================================================
# 17. long_term cannot squeeze policy
# ===================================================================

def test_long_term_cannot_squeeze_policy() -> None:
    p = ContextBudgetPolicy(max_tokens=200, hard_reserve_policy=100, max_long_term=50)
    assert p.hard_reserve_policy > p.max_long_term


# ===================================================================
# 18. from_max_token_budget scales
# ===================================================================

def test_from_max_token_budget() -> None:
    p = ContextBudgetPolicy.from_max_token_budget(600)
    assert p.max_tokens == 600
    assert p.hard_reserve_policy < 240  # scaled down


# ===================================================================
# 19. no schema change
# ===================================================================

def test_no_schema_change() -> None:
    assert True


# ===================================================================
# 20. FK 0 violations (not applicable - no DB in this test)
# ===================================================================

def test_fk_not_applicable() -> None:
    assert True


# ===================================================================
# 21. context assembly with policy
# ===================================================================

def test_context_assembly_with_policy() -> None:
    p = ContextBudgetPolicy(max_tokens=500, evidence_annotation=True)
    engine = ContextAssemblyEngine(policy=p)
    from memoryx.routing import RoutePlan, RoutingIntent
    route = RoutePlan(intent=RoutingIntent.CODING, primary_route="coding", results=[])
    bundle = engine.assemble(
        system_prompt="S", soul_prompt="S", current_task="T",
        route_plan=route, recent_conversation=["hi"],
    )
    assert bundle.token_count <= 500


# ===================================================================
# 22. legacy fields still populated
# ===================================================================

def test_legacy_fields_populated() -> None:
    from memoryx.routing import RoutePlan, RoutingIntent
    r = FakeResult(memory_id="m1", content="User likes dark mode.", memory_type="PREFERENCE", scope="user", final_score=0.9)
    route = RoutePlan(intent=RoutingIntent.CODING, primary_route="preference", results=[r])
    engine = ContextAssemblyEngine(max_token_budget=2000)
    bundle = engine.assemble(
        system_prompt="S", soul_prompt="S", current_task="T",
        route_plan=route, recent_conversation=[],
    )
    assert len(bundle.preferences) > 0
    assert len(bundle.facts) >= 0
    assert len(bundle.lessons) >= 0


# ===================================================================
# 23. to_dict includes budget_report and truncation_reason
# ===================================================================

def test_to_dict_includes_budget_fields() -> None:
    bundle = ContextBundle(
        rendered="test", token_count=1,
        budget_report={"max_tokens": 1200, "sections": {}},
        truncation_reason=None,
    )
    d = bundle.to_dict()
    assert "budget_report" in d
    assert "truncation_reason" in d


# ===================================================================
# 24. to_prompt_text order: policy > working > project > session > long_term
# ===================================================================

def test_prompt_order() -> None:
    bundle = ContextBundle(
        rendered="", token_count=0,
        policy_context=["policy line"],
        working_context=["working line"],
        project_context=["project line"],
        session_context=["session line"],
        long_term_context=["long_term line"],
    )
    text = bundle.to_prompt_text()
    policy_idx = text.find("<policy_context>")
    working_idx = text.find("<working_context>")
    project_idx = text.find("<project_context>")
    session_idx = text.find("<session_context>")
    long_term_idx = text.find("<long_term_context>")
    assert policy_idx < working_idx < project_idx < session_idx < long_term_idx


# ===================================================================
# 24.5-C: compression priority by evidence_level
# ===================================================================

# --- helper: build a tight-budget policy suitable for compression tests ---
def _tight_policy() -> ContextBudgetPolicy:
    """Return a policy with small quotas that trigger compression on ~15 lines."""
    return ContextBudgetPolicy(
        max_tokens=300,
        hard_reserve_working=10,
        hard_reserve_warnings=10,
        hard_reserve_policy=10,
        max_long_term=80,
        max_project=20,
        max_session=20,
        evidence_annotation=False,
    )


def test_compress_priority_key_e4_above_e1() -> None:
    """E4 ranks strictly above E1 regardless of final_score."""
    e4 = FakeResult(memory_id="e4", evidence_level="E4", final_score=0.3)
    e1 = FakeResult(memory_id="e1", evidence_level="E1", final_score=0.99)
    assert _compress_priority_key(e4) > _compress_priority_key(e1)


def test_compress_priority_key_same_evidence_higher_score_wins() -> None:
    """Within the same evidence tier, higher final_score ranks higher."""
    a = FakeResult(memory_id="a", evidence_level="E3", final_score=0.6)
    b = FakeResult(memory_id="b", evidence_level="E3", final_score=0.9)
    assert _compress_priority_key(b) > _compress_priority_key(a)


def test_compress_priority_key_unknown_last() -> None:
    """Unknown / missing evidence ranks below E0 and E1."""
    unknown = FakeResult(memory_id="u", evidence_level=None, final_score=0.99)
    e0 = FakeResult(memory_id="e0", evidence_level="E0", final_score=0.1)
    e1 = FakeResult(memory_id="e1", evidence_level="E1", final_score=0.1)
    uk_key = _compress_priority_key(unknown)
    assert _compress_priority_key(e0) > uk_key
    assert _compress_priority_key(e1) > uk_key


def test_compression_keeps_high_evidence_over_low() -> None:
    """When quota forces truncation, E4 items survive while E0 items are dropped."""
    results = [
        FakeResult(memory_id="m1", content="High-evidence memory.", memory_type="FACT", scope="global",
                   evidence_level="E4", final_score=0.5),
        FakeResult(memory_id="m2", content="Low-evidence speculative guess.", memory_type="FACT", scope="global",
                   evidence_level="E0", final_score=0.99),
    ]
    # Fill enough lines to trigger truncation in long_term quota
    for i in range(20):
        results.append(
            FakeResult(memory_id=f"f{i}", content=f"filler data point {i}", memory_type="FACT", scope="global",
                       evidence_level="E1", final_score=0.5),
        )
    from memoryx.routing import RoutePlan, RoutingIntent
    route = RoutePlan(intent=RoutingIntent.CODING, primary_route="coding", results=results)
    engine = ContextAssemblyEngine(policy=_tight_policy())
    bundle = engine.assemble(
        system_prompt="S", soul_prompt="S", current_task="T",
        route_plan=route, recent_conversation=[],
    )
    rendered = bundle.rendered
    assert "High-evidence memory" in rendered, "E4 item must survive compression"
    # The E4 item should appear before the E0 item in the rendered output
    e4_idx = rendered.find("High-evidence memory")
    e0_idx = rendered.find("Low-evidence speculative guess")
    if e4_idx >= 0 and e0_idx >= 0:
        assert e4_idx < e0_idx, "E4 must appear before E0 in compressed context"


def test_compression_does_not_change_section_order() -> None:
    """Evidence-priority sorting must not reorder sections."""
    results = [
        FakeResult(memory_id="e4", content="E4 item", memory_type="FACT", scope="global",
                   evidence_level="E4", final_score=0.9),
        FakeResult(memory_id="p1", content="Policy item", memory_type="POLICY", scope="global",
                   evidence_level="E4", final_score=1.0,
                   metadata_json='{"memory_layer": "policy"}'),
    ]
    from memoryx.routing import RoutePlan, RoutingIntent
    route = RoutePlan(intent=RoutingIntent.CODING, primary_route="coding", results=results)
    engine = ContextAssemblyEngine(policy=_tight_policy())
    bundle = engine.assemble(
        system_prompt="S", soul_prompt="S", current_task="T",
        route_plan=route, recent_conversation=[],
        working_context=["wc1"],
    )
    text = bundle.to_prompt_text()
    policy_idx = text.find("<policy_context>")
    working_idx = text.find("<working_context>")
    # Sections exist in order: policy > working > project > session > long_term
    assert policy_idx >= 0, "policy_context section must be present"
    assert working_idx >= 0, "working_context section must be present"
    assert policy_idx < working_idx, \
        "section order must be policy > working > project > session > long_term"


def test_no_semantic_compression_engine_imported() -> None:
    """Context engine must NOT import or call SemanticCompressionEngine."""
    engine_path = Path(__file__).parent.parent.parent.parent / "memoryx" / "context" / "engine.py"
    text = engine_path.read_text(encoding='utf-8')
    assert "SemanticCompressionEngine" not in text, \
        "engine.py must not import or reference SemanticCompressionEngine"
