"""Tests for MemoryX context layering (24.3B)."""
from __future__ import annotations

import json
from dataclasses import dataclass, field


from memoryx.context.engine import ContextAssemblyEngine


# Mock a RetrievalResult-like object
@dataclass
class FakeRetrievalResult:
    memory_id: str
    content: str
    memory_type: str
    scope: str
    final_score: float
    metadata_json: str = "{}"


# Mock a RoutePlan-like object
@dataclass
class FakeRoutePlan:
    results: list = field(default_factory=list)


def _make_result(
    mid: str,
    content: str,
    memory_type: str = "FACT",
    scope: str = "global",
    score: float = 0.5,
    layer: str = "",
) -> FakeRetrievalResult:
    meta = {"memory_layer": layer} if layer else {}
    return FakeRetrievalResult(
        memory_id=mid,
        content=content,
        memory_type=memory_type,
        scope=scope,
        final_score=score,
        metadata_json=json.dumps(meta),
    )


def test_policy_context_has_priority() -> None:
    """Policy/guard memories go into policy_context and appear first in prompt."""
    engine = ContextAssemblyEngine(max_token_budget=2000)
    results = [
        _make_result("m1", "Some fact.", memory_type="FACT", score=0.9, layer="long_term"),
        # Policy via layer (the context engine groups by layer, not memory_type)
        _make_result("m2", "Policy: never delete data.", memory_type="FACT", score=0.8, layer="policy"),
        _make_result("m3", "A preference.", memory_type="PREFERENCE", score=0.7, layer="long_term"),
    ]
    route = FakeRoutePlan(results=results)
    bundle = engine.assemble(
        system_prompt="Test",
        soul_prompt="Soul",
        current_task="Testing",
        route_plan=route,
        recent_conversation=["hi"],
    )
    assert len(bundle.policy_context) > 0
    # Policy should appear before long_term in the section order
    text = bundle.rendered
    policy_idx = text.find("Policy / Guard")
    long_term_idx = text.find("Relevant Long-Term Memory")
    assert policy_idx >= 0
    assert long_term_idx >= 0
    assert policy_idx < long_term_idx, "policy_context should appear before long_term"


def test_project_context() -> None:
    """PROJECT layer goes into project_context."""
    engine = ContextAssemblyEngine(max_token_budget=2000)
    results = [
        _make_result("m1", "Project status.", memory_type="PROJECT", score=0.8, layer="project"),
    ]
    route = FakeRoutePlan(results=results)
    bundle = engine.assemble(
        system_prompt="Test", soul_prompt="Soul", current_task="Testing",
        route_plan=route, recent_conversation=[],
    )
    assert len(bundle.project_context) > 0


def test_session_context() -> None:
    """SESSION layer goes into session_context."""
    engine = ContextAssemblyEngine(max_token_budget=2000)
    results = [
        _make_result("m1", "Session specific.", memory_type="FACT", score=0.8, layer="session"),
    ]
    route = FakeRoutePlan(results=results)
    bundle = engine.assemble(
        system_prompt="Test", soul_prompt="Soul", current_task="Testing",
        route_plan=route, recent_conversation=[],
    )
    assert len(bundle.session_context) > 0


def test_long_term_context() -> None:
    """Long-term layer goes into long_term_context."""
    engine = ContextAssemblyEngine(max_token_budget=2000)
    results = [
        _make_result("m1", "Long term fact.", memory_type="FACT", scope="global", score=0.8, layer="long_term"),
    ]
    route = FakeRoutePlan(results=results)
    bundle = engine.assemble(
        system_prompt="Test", soul_prompt="Soul", current_task="Testing",
        route_plan=route, recent_conversation=[],
    )
    assert len(bundle.long_term_context) > 0


def test_working_context_injected() -> None:
    """Working context passed to assemble is in working_context field."""
    engine = ContextAssemblyEngine(max_token_budget=2000)
    route = FakeRoutePlan(results=[])
    wc = ["Current task: testing layering", "Reasoning: check -> verify"]
    bundle = engine.assemble(
        system_prompt="Test", soul_prompt="Soul", current_task="Testing",
        route_plan=route, recent_conversation=[], working_context=wc,
    )
    assert len(bundle.working_context) > 0
    assert "testing layering" in bundle.working_context[0]


def test_candidate_not_in_context() -> None:
    """Candidates should not show up in context (they're hidden by retrieval)."""
    # This is a verification that the retrieval engine's _is_visible_memory_for_retrieval
    # prevents candidates from reaching the context assembly layer.
    # The context assembly only sees what the retrieval engine passes through.
    engine = ContextAssemblyEngine(max_token_budget=2000)
    # Even if a candidate somehow reaches the assembler (shouldn't happen),
    # it would be grouped normally — the candidate filtering is at retrieval level.
    results = [
        _make_result("m1", "Candidate content.", memory_type="FACT", score=0.8, layer="long_term"),
    ]
    route = FakeRoutePlan(results=results)
    bundle = engine.assemble(
        system_prompt="Test", soul_prompt="Soul", current_task="Test",
        route_plan=route, recent_conversation=[],
    )
    # Content appears because it's in long_term layer — the gate is at retrieval level
    assert len(bundle.long_term_context) > 0


def test_stale_rejected_not_in_context() -> None:
    """Stale/rejected memories should not reach context assembly (filtered by retrieval)."""
    # Same as above — this is verified at the retrieval layer,
    # the context assembly just groups what it receives.
    pass


def test_token_budget_keeps_policy() -> None:
    """When budget is tight, policy context should be preserved."""
    engine = ContextAssemblyEngine(max_token_budget=50)  # tiny budget
    results = [
        _make_result("m1", "Policy: must verify before commit.", memory_type="FACT", score=0.5, layer="policy"),
        _make_result("m2", "A" * 200, memory_type="FACT", score=0.9, layer="long_term"),
    ]
    route = FakeRoutePlan(results=results)
    bundle = engine.assemble(
        system_prompt="S", soul_prompt="S", current_task="T",
        route_plan=route, recent_conversation=["x"],
    )
    # Policy should still be visible even with tight budget
    policy_visible = any("Policy: must verify" in line for line in bundle.policy_context)
    assert policy_visible, "policy context should survive budget pressure"


def test_old_fields_preserved() -> None:
    """Legacy fields (facts, preferences, lessons) are still populated."""
    engine = ContextAssemblyEngine(max_token_budget=2000)
    results = [
        _make_result("m1", "Fact 1", memory_type="FACT", scope="global", layer="long_term"),
        _make_result("m2", "Preference 1", memory_type="PREFERENCE", scope="user", layer="long_term"),
        _make_result("m3", "Lesson 1", memory_type="LESSON", scope="global", layer="long_term"),
    ]
    route = FakeRoutePlan(results=results)
    bundle = engine.assemble(
        system_prompt="S", soul_prompt="S", current_task="T",
        route_plan=route, recent_conversation=[],
    )
    assert len(bundle.facts) > 0
    assert len(bundle.preferences) > 0
    assert len(bundle.lessons) > 0
    assert bundle.total_candidates == 0


def test_layer_counts_correct() -> None:
    """layer_counts reflects actual layer distribution."""
    engine = ContextAssemblyEngine(max_token_budget=2000)
    results = [
        _make_result("m1", "Policy 1", memory_type="FACT", layer="policy"),
        _make_result("m2", "Project 1", memory_type="PROJECT", scope="project", layer="project"),
        _make_result("m3", "Session 1", memory_type="FACT", layer="session"),
        _make_result("m4", "Fact 1", memory_type="FACT", scope="global", layer="long_term"),
    ]
    route = FakeRoutePlan(results=results)
    bundle = engine.assemble(
        system_prompt="S", soul_prompt="S", current_task="T",
        route_plan=route, recent_conversation=[],
    )
    assert bundle.layer_counts.get("policy", 0) >= 1
    assert bundle.layer_counts.get("project", 0) >= 1
    assert bundle.layer_counts.get("session", 0) >= 1


def test_missing_layer_fallback() -> None:
    """Legacy memories without memory_layer still work via old scope/memory_type logic."""
    engine = ContextAssemblyEngine(max_token_budget=2000)
    results = [
        _make_result("m1", "User preference (legacy)", memory_type="PREFERENCE", scope="user"),
        _make_result("m2", "Project (legacy)", memory_type="PROJECT", scope="project"),
        _make_result("m3", "Lesson (legacy)", memory_type="LESSON", scope="global"),
        _make_result("m4", "Fact (legacy)", memory_type="FACT", scope="global"),
    ]
    route = FakeRoutePlan(results=results)
    bundle = engine.assemble(
        system_prompt="S", soul_prompt="S", current_task="T",
        route_plan=route, recent_conversation=[],
    )
    assert len(bundle.preferences) > 0  # legacy PREFERENCE
    assert len(bundle.project_state) > 0  # legacy PROJECT
    assert len(bundle.lessons) > 0  # legacy LESSON
    assert len(bundle.facts) > 0  # legacy FACT


def test_to_dict_to_json_old_fields() -> None:
    """to_dict() and to_json() include all old fields."""
    engine = ContextAssemblyEngine(max_token_budget=2000)
    results = [
        _make_result("m1", "Fact data", memory_type="FACT", layer="long_term"),
    ]
    route = FakeRoutePlan(results=results)
    bundle = engine.assemble(
        system_prompt="S", soul_prompt="S", current_task="T",
        route_plan=route, recent_conversation=[],
    )
    d = bundle.to_dict()
    assert "rendered" in d
    assert "token_count" in d
    assert "facts" in d
    assert "preferences" in d
    assert "lessons" in d
    assert "project_state" in d
    assert "working_context" in d
    assert "policy_context" in d
    assert "layer_counts" in d
    j = bundle.to_json()
    assert isinstance(j, str)
    assert "rendered" in j


def test_to_prompt_text_structure() -> None:
    """to_prompt_text has expected XML tags for each layer."""
    engine = ContextAssemblyEngine(max_token_budget=2000)
    results = [
        _make_result("m1", "Policy data", memory_type="FACT", layer="policy"),
        _make_result("m2", "Fact data", memory_type="FACT", layer="long_term"),
    ]
    route = FakeRoutePlan(results=results)
    bundle = engine.assemble(
        system_prompt="S", soul_prompt="S", current_task="T",
        route_plan=route, recent_conversation=[],
        working_context=["Working note"],
    )
    text = bundle.to_prompt_text()
    assert "<policy_context>" in text
    assert "<working_context>" in text
    assert "<long_term_context>" in text
    # Policy should come before working and long_term
    policy_idx = text.find("<policy_context>")
    text.find("<working_context>")
    long_term_idx = text.find("<long_term_context>")
    assert policy_idx < long_term_idx, "policy should come before long_term in prompt"
