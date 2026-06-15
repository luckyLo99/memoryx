from __future__ import annotations

import sqlite3

from memoryx.retrieval.fusion import make_ranked_candidates, reciprocal_rank_fusion
from .retriever import Retriever
from memoryx.retrieval.scorer import compute_final_score, confidence_label, score_to_explanation
from .types import RetrievalResult, SearchOptions
from memoryx.embeddings.vector_store import NullVectorProvider, VectorProvider

class HybridRetriever:
    def __init__(
        self, db_path: str,
        vector_provider: VectorProvider | None = None,
        *,
        engine: Any = None,
    ):
        self.db_path = db_path
        self.vector_provider = vector_provider or NullVectorProvider()
        self.lite_retriever = Retriever(db_path)
        self._engine = engine

    def search(self, query: str, limit: int = 10, options: SearchOptions | None = None) -> list[RetrievalResult]:
        if self._engine is not None:
            return self._engine_search(query, limit, options)
        opts = options or SearchOptions(limit=limit, mode="auto")

        if opts.mode == "lite" or (opts.mode == "auto" and not self.vector_provider.available):
            return self.lite_retriever.search(query, limit=limit, options=opts)

        if opts.mode in {"hybrid", "auto"}:
            return self._hybrid_search(query, limit, opts)

        if opts.mode == "vector":
            return self._vector_only_search(query, limit, opts)

        return self.lite_retriever.search(query, limit=limit, options=opts)

    def _engine_search(self, query: str, limit: int, options: SearchOptions | None) -> list[RetrievalResult]:
        """Delegate to HybridRetrievalEngine and adapt results."""
        import asyncio
        from memoryx.retrieval.models import RetrievalResult as NewResult
        opts = options or SearchOptions(limit=limit)
        explain = getattr(opts, "explain", False)
        try:
            results: list[NewResult] = asyncio.run(
                self._engine.retrieve(
                    query=query, query_vector=[], limit=limit, explain_scores=explain,
                )
            )
        except Exception:
            return self.lite_retriever.search(query, limit=limit, options=opts)
        mapped: list[RetrievalResult] = []
        for r in results:
            label = "high" if r.final_score >= 0.7 else "medium" if r.final_score >= 0.4 else "low"
            mapped.append(RetrievalResult(
                claim_id=getattr(r, "memory_id", ""),
                content=r.content,
                claim_type=getattr(r, "memory_type", "FACT"),
                status="active",
                final_score=r.final_score,
                confidence_label=label,
                explanation={"delegated_to": "HybridRetrievalEngine"} if explain else {},
            ))
        return mapped[:limit]

    def _hybrid_search(self, query: str, limit: int, opts: SearchOptions) -> list[RetrievalResult]:
        fts_ids = self._fts_claim_ids(query, limit * 4, opts.include_inactive)
        vector_hits = self.vector_provider.search(query, limit=limit * 4) if self.vector_provider.available else []
        vector_ids = [hit.claim_id for hit in vector_hits]
        vector_scores = {hit.claim_id: hit.score for hit in vector_hits}

        rrf = reciprocal_rank_fusion([
            make_ranked_candidates(fts_ids, "fts"),
            make_ranked_candidates(vector_ids, "vector"),
        ])
        if not rrf:
            return []

        rows = self._load_claim_rows(list(rrf.keys()), opts.include_inactive)
        results: list[RetrievalResult] = []
        for row in rows:
            claim_id = row["claim_id"]
            score = compute_final_score(
                bm25_score=None, vector_score=vector_scores.get(claim_id),
                updated_at=row["updated_at"], last_accessed_at=row["last_accessed_at"],
                access_count=row["access_count"] or 0,
                importance=row["importance"] or 0.5, confidence=row["confidence"] or 0.5,
                status=row["status"], rrf_score=rrf.get(claim_id),
            )
            label = confidence_label(score.final_score)
            if opts.reject_low_confidence and (label == "rejected" or score.final_score < opts.min_score):
                continue
            explanation = score_to_explanation(score) if opts.explain else {}
            explanation["fusion"] = {"method": "rrf", "fts_present": claim_id in set(fts_ids), "vector_present": claim_id in set(vector_ids)}
            results.append(RetrievalResult(claim_id=claim_id, content=row["content"], claim_type=row["claim_type"], status=row["status"], final_score=score.final_score, confidence_label=label, explanation=explanation))

        results = sorted(results, key=lambda r: r.final_score, reverse=True)[:limit]
        with sqlite3.connect(self.db_path) as con:
            self.lite_retriever._record_retrieval_events(con, query, results, "hybrid")
            self.lite_retriever._reinforce_access(con, [r.claim_id for r in results])
            con.commit()
        return results

    def _vector_only_search(self, query: str, limit: int, opts: SearchOptions) -> list[RetrievalResult]:
        if not self.vector_provider.available:
            return []
        vector_hits = self.vector_provider.search(query, limit=limit * 4)
        vector_scores = {hit.claim_id: hit.score for hit in vector_hits}
        rows = self._load_claim_rows([hit.claim_id for hit in vector_hits], opts.include_inactive)
        results: list[RetrievalResult] = []
        for row in rows:
            claim_id = row["claim_id"]
            score = compute_final_score(bm25_score=None, vector_score=vector_scores.get(claim_id), updated_at=row["updated_at"], last_accessed_at=row["last_accessed_at"], access_count=row["access_count"] or 0, importance=row["importance"] or 0.5, confidence=row["confidence"] or 0.5, status=row["status"])
            label = confidence_label(score.final_score)
            if opts.reject_low_confidence and (label == "rejected" or score.final_score < opts.min_score):
                continue
            results.append(RetrievalResult(claim_id=claim_id, content=row["content"], claim_type=row["claim_type"], status=row["status"], final_score=score.final_score, confidence_label=label, explanation=score_to_explanation(score) if opts.explain else {}))
        return sorted(results, key=lambda r: r.final_score, reverse=True)[:limit]

    def _fts_claim_ids(self, query: str, limit: int, include_inactive: bool) -> list[str]:
        status_clause = "" if include_inactive else "AND c.status = 'active'"
        with sqlite3.connect(self.db_path) as con:
            rows = con.execute(f"SELECT c.claim_id FROM fts_memories JOIN claims c ON c.claim_id = fts_memories.claim_id WHERE fts_memories MATCH ? {status_clause} ORDER BY bm25(fts_memories) ASC LIMIT ?", (query, limit)).fetchall()  # nosec B608
        return [row[0] for row in rows]

    def _load_claim_rows(self, claim_ids: list[str], include_inactive: bool) -> list[sqlite3.Row]:
        if not claim_ids:
            return []
        ph = ",".join("?" for _ in claim_ids)
        sc = "" if include_inactive else "AND status = 'active'"
        with sqlite3.connect(self.db_path) as con:
            con.row_factory = sqlite3.Row
            rows = list(con.execute(f"SELECT claim_id, claim_type, content, status, confidence, importance, updated_at, last_accessed_at, access_count FROM claims WHERE claim_id IN ({ph}) {sc}", claim_ids).fetchall())  # nosec B608
        order = {cid: i for i, cid in enumerate(claim_ids)}
        return sorted(rows, key=lambda r: order.get(r["claim_id"], 10**9))
