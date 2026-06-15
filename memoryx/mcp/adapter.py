from __future__ import annotations

import asyncio
from typing import Any

from memoryx.context_budget import BudgetedContextAssembler
from memoryx.mcp._compat import HermesAdapter, MemoryKernel
from memoryx.retrieval import HybridRetriever
from memoryx.retrieval import SearchOptions
from memoryx.embeddings.vector_store import NullVectorProvider
from .session import current_mcp_session


class MemoryXMCPAdapter:
    def __init__(self, db_path: str):
        self.db_path = db_path

    def signal(self, args: dict[str, Any]) -> dict[str, Any]:
        session = current_mcp_session()
        adapter = HermesAdapter(self.db_path)
        try:
            return adapter.signal(
                event_type=args.get("event_type", "user_message"),
                text=args["text"],
                metadata=args.get("metadata") or {},
                session_id=args.get("session_id") or session.session_id,
                agent_id=args.get("agent_id") or session.agent_id,
                user_id=args.get("user_id") or session.user_id,
            )
        finally:
            adapter.kernel.close()

    def query(self, args: dict[str, Any]) -> dict[str, Any]:
        session = current_mcp_session()
        assembler = BudgetedContextAssembler(self.db_path)
        return assembler.assemble(
            query=args["query"],
            session_history=args.get("session_history") or [],
            limit=int(args.get("limit", 6)),
            session_id=args.get("session_id") or session.session_id,
            agent_id=args.get("agent_id") or session.agent_id,
            user_id=args.get("user_id") or session.user_id,
            request_id=args.get("request_id"),
            mode=args.get("mode"),
            previous_pack_id=args.get("previous_pack_id"),
        )

    def commit(self, args: dict[str, Any]) -> dict[str, Any]:
        adapter = HermesAdapter(self.db_path)
        try:
            return adapter.commit(args["claim_id"], args.get("params") or {})
        finally:
            adapter.kernel.close()

    def revoke(self, args: dict[str, Any]) -> dict[str, Any]:
        kernel = MemoryKernel(self.db_path)
        try:
            kernel.revoke_claim(args["claim_id"], reason=args.get("reason", "mcp_revoke"))
            return {"claim_id": args["claim_id"], "status": "revoked"}
        finally:
            kernel.close()

    def debug(self, args: dict[str, Any]) -> dict[str, Any]:
        """Raw retrieval debug - FTS candidates + final results."""
        query = args["query"]
        limit = int(args.get("limit", 10))
        import sqlite3
        with sqlite3.connect(self.db_path) as con:
            con.row_factory = sqlite3.Row
            raw = [dict(r) for r in con.execute(
                "SELECT c.claim_id, c.content, c.status, bm25(fts_memories) AS bm25_score FROM fts_memories JOIN claims c ON c.claim_id = fts_memories.claim_id WHERE fts_memories MATCH ? ORDER BY bm25_score ASC LIMIT ?",
                (query, limit * 2)).fetchall()]
        retriever = HybridRetriever(self.db_path, NullVectorProvider())
        final = retriever.search(query, limit=limit, options=SearchOptions(limit=limit, mode="auto", min_score=0.0, reject_low_confidence=False))
        return {
            "query": query,
            "raw_fts_candidates": raw,
            "final_results": [{"claim_id": r.claim_id, "content": r.content, "final_score": r.final_score,
                               "confidence_label": r.confidence_label, "status": r.status, "claim_type": r.claim_type} for r in final]
        }

    def stats(self, args: dict[str, Any] | None = None) -> dict[str, Any]:
        with MemoryKernel(self.db_path) as k:
            conn = k.conn
            all_tables = ["evidence_events","claims","claim_versions","retrieval_events","claim_edges","memory_edges"]
            existing = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
            row_counts = {}
            for t in all_tables:
                try:
                    row_counts[t] = conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] if t in existing else -1  # nosec B608
                except Exception:
                    row_counts[t] = -1
            return {'row_counts': row_counts, 'tables': all_tables}

    def quality_gate(self, args: dict[str, Any]) -> dict[str, Any]:
        return {"passed": True, "note": "quality gate stub"}

    def audit_export(self, args: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True, "note": "audit export stub"}


class AsyncMemoryXMCPAdapter:
    def __init__(self, db_path: str):
        self.sync = MemoryXMCPAdapter(db_path)

    async def signal(self, args): return await asyncio.to_thread(self.sync.signal, args)
    async def query(self, args): return await asyncio.to_thread(self.sync.query, args)
    async def commit(self, args): return await asyncio.to_thread(self.sync.commit, args)
    async def revoke(self, args): return await asyncio.to_thread(self.sync.revoke, args)
    async def debug(self, args): return await asyncio.to_thread(self.sync.debug, args)
    async def stats(self, args): return await asyncio.to_thread(self.sync.stats, args or {})
    async def quality_gate(self, args): return await asyncio.to_thread(self.sync.quality_gate, args)
    async def audit_export(self, args): return await asyncio.to_thread(self.sync.audit_export, args)
