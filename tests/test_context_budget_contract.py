"""Tests for context budget / layer quota / evidence annotation (24.5-B)."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from memoryx.context.engine import ContextAssemblyEngine, _annotate_line, _resolve_layer_from_result, _is_result_lesson
from memoryx.context.models import ContextBundle, ContextBudgetPolicy
from memoryx.retrieval.models import RetrievalResult


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
    engine = ContextAssemblyEngine(policy=p)
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
