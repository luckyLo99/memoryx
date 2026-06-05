from __future__ import annotations

from typing import Any

from .kernel import MemoryKernel
from memoryx.core.hybrid_retriever import HybridRetriever
from memoryx.core.types import SearchOptions
from memoryx.core.vector import NullVectorProvider


class HermesAdapter:
    """
    Hermes Adapter with budgeted context by default.

    P0 guarantee:
    - query() is budgeted by default.
    - raw_query() is the explicit debug path.
    """

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.kernel = MemoryKernel(db_path)
        from memoryx.context_budget import BudgetedContextAssembler
        self.ctx = BudgetedContextAssembler(db_path)

    def signal(self, event_type, text, metadata=None, session_id=None, agent_id=None, user_id=None) -> dict[str, Any]:
        """Ingest an interaction signal into MemoryX."""
        ev = self.kernel.create_evidence(
            event_type, text,
            session_id=session_id, agent_id=agent_id, user_id=user_id,
            metadata=metadata or {},
        )
        cid = self.kernel.create_claim("fact", text, [ev], confidence=0.65, importance=0.65)
        return {"event_id": ev, "claim_id": cid}

    def query(self, query, session_history=None, limit=6, session_id=None, agent_id=None, user_id=None, request_id=None, mode=None, previous_pack_id=None) -> dict[str, Any]:
        """Safe default query. Returns budgeted context pack."""
        return self.ctx.assemble(
            query=query, session_history=session_history or [], limit=limit,
            session_id=session_id, agent_id=agent_id, user_id=user_id, request_id=request_id,
            mode=mode, previous_pack_id=previous_pack_id,
        )

    def raw_query(self, query, session_history=None, limit=50) -> dict[str, Any]:
        """Explicit debug query path. Not for default prompt injection."""
        retriever = HybridRetriever(self.db_path, NullVectorProvider())
        results = retriever.search(query, limit=limit, options=SearchOptions(limit=limit, mode="auto", min_score=0.0, reject_low_confidence=False))
        return {
            "ok": True, "query": query,
            "results": [{"claim_id": r.claim_id, "content": r.content, "score": r.final_score, "type": r.claim_type, "status": r.status, "confidence": r.confidence_label} for r in results],
            "session_context": session_history or [],
            "provenance": {"mode": "raw_query_explicit_debug_only", "count": len(results)},
        }

    def commit(self, claim_id, params=None) -> dict[str, Any]:
        c = self.kernel.get_claim(claim_id)
        if not c:
            raise ValueError(f"claim not found:{claim_id}")
        return {"claim_id": claim_id, "status": c["status"], "claim": c, "params": params or {}}
