from __future__ import annotations
import uuid
from typing import Any
from memoryx.core.hybrid_retriever import HybridRetriever
from memoryx.core.types import SearchOptions
from memoryx.embeddings.vector_store import NullVectorProvider
from .diff import ContextPackHistory
from .packer import ContextItem, ContextPacker
from .planner import AdaptiveContextPlanner
from .policy import ContextBudgetPolicy
from .run_guard import ActiveRequestStore
from .session_summary import SessionSummaryStore

class BudgetedContextAssembler:
    def __init__(self, db_path: str, policy: ContextBudgetPolicy | None = None):
        self.db_path = db_path; self.policy = policy
        self.guard = ActiveRequestStore(db_path); self.summary_store = SessionSummaryStore(db_path); self.history = ContextPackHistory(db_path)

    def assemble(self, *, query: str, session_id=None, agent_id=None, user_id=None, request_id=None,
                 session_history=None, limit=None, begin_request=True, mode=None, previous_pack_id=None) -> dict[str, Any]:
        rid = request_id or uuid.uuid4().hex; pack_id = uuid.uuid4().hex
        planner = AdaptiveContextPlanner(); plan = planner.plan(query, requested_mode=mode)
        policy = self.policy or plan.policy; packer = ContextPacker(policy)
        if begin_request:
            lease = self.guard.begin_request(session_id=session_id, task_text=query, request_id=rid); rid = lease.request_id
        stale = self.guard.reject_if_stale(rid, session_id)
        if stale: return stale

        retriever = HybridRetriever(self.db_path, NullVectorProvider())
        rl = min(max(limit or policy.max_memory_items * 2, 1), policy.max_memory_items * 4)
        hits = retriever.search(query, limit=rl, options=SearchOptions(limit=rl, mode="auto", min_score=0.0, reject_low_confidence=False, include_inactive=False, explain=policy.include_explanations))
        items: list[ContextItem] = []

        if session_id and session_history and plan.profile.include_session_summary:
            summary = self.summary_store.upsert_from_history(session_id, session_history, max_summary_tokens=min(512, policy.max_item_tokens))
            if summary.summary:
                items.append(ContextItem(f"session_summary:{session_id}", "session_summary", summary.summary, 0.70, "session_summary", {"summary_updated_at": summary.updated_at, "turn_count": summary.turn_count}))

        for hit in hits:
            meta = {"claim_type": hit.claim_type, "status": hit.status}
            if policy.include_explanations: meta["explanation"] = hit.explanation
            items.append(ContextItem(hit.claim_id, "relevant_memories", hit.content, float(hit.final_score), hit.claim_type, meta))

        prev_ids = set(self.history.get_item_ids(previous_pack_id))
        pack = packer.pack(request_id=rid, session_id=session_id, query=query, items=items, mode=plan.mode,
                           pack_id=pack_id, previous_item_ids=prev_ids, omit_repeated_items=plan.profile.omit_repeated_items and bool(previous_pack_id))
        included_ids = [item["id"] for sec in pack.sections.values() for item in sec if item.get("id")]
        self.history.record_pack(pack_id=pack_id, session_id=session_id, request_id=rid, query=query, item_ids=included_ids, used_tokens=pack.used_tokens)

        stale2 = self.guard.reject_if_stale(rid, session_id)
        if stale2: return stale2
        self.guard.complete_request(rid, "completed")
        return {"ok": True, "request_id": rid, "session_id": session_id, "agent_id": agent_id, "user_id": user_id,
                "context_pack": pack.to_dict(),
                "instruction_context": [item for item in pack.sections.get("relevant_memories", []) if item.get("type") in {"instruction", "preference", "task_state"}],
                "evidence_context": [item for item in pack.sections.get("relevant_memories", []) if item.get("type") not in {"instruction", "preference", "task_state"}],
                "session_context": [],
                "provenance": {"assembler": "BudgetedContextAssembler", "planner": "AdaptiveContextPlanner",
                    "mode": plan.mode, "plan_reason": plan.reason, "schema": pack.schema, "pack_id": pack_id,
                    "previous_pack_id": previous_pack_id, "max_tokens": pack.max_tokens, "used_tokens": pack.used_tokens,
                    "included_items": pack.included_items, "dropped_items": pack.dropped_items,
                    "budget_policy": {"max_context_tokens": policy.max_context_tokens, "max_memory_items": policy.max_memory_items,
                        "max_item_tokens": policy.max_item_tokens, "min_score": policy.min_score,
                        "session_history_injected_raw": False, "session_summary_enabled": plan.profile.include_session_summary}}}
