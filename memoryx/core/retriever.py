from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone

from .scoring import compute_final_score, confidence_label, score_to_explanation
from .types import RetrievalResult, SearchOptions

def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

class Retriever:
    def __init__(self, db_path: str):
        self.db_path = db_path

    def search(
        self,
        query: str,
        limit: int = 10,
        options: SearchOptions | None = None,
    ) -> list[RetrievalResult]:
        opts = options or SearchOptions(limit=limit)
        effective_limit = opts.limit or limit

        with sqlite3.connect(self.db_path) as con:
            con.row_factory = sqlite3.Row
            rows = self._fts_candidates(con, query, effective_limit * 4, opts.include_inactive)
            results = self._score_rows(rows, opts)

            if opts.reject_low_confidence:
                results = [
                    r for r in results
                    if r.confidence_label != "rejected" and r.final_score >= opts.min_score
                ]

            results = sorted(results, key=lambda r: r.final_score, reverse=True)[:effective_limit]

            if opts.record_access and results:
                self._record_retrieval_events(con, query, results, "lite")
                self._reinforce_access(con, [r.claim_id for r in results])
                con.commit()

            return results

    def _fts_candidates(
        self, con: sqlite3.Connection, query: str, limit: int, include_inactive: bool
    ) -> list[sqlite3.Row]:
        status_clause = "" if include_inactive else "AND c.status = 'active'"
        sql = f"""
            SELECT c.claim_id, c.claim_type, c.content, c.status,
                   c.confidence, c.importance, c.updated_at,
                   c.last_accessed_at, c.access_count,
                   bm25(fts_memories) AS bm25_score
            FROM fts_memories
            JOIN claims c ON c.claim_id = fts_memories.claim_id
            WHERE fts_memories MATCH ?
            {status_clause}
            ORDER BY bm25_score ASC LIMIT ?
        """
        return list(con.execute(sql, (query, limit)).fetchall())

    def _score_rows(self, rows: list[sqlite3.Row], opts: SearchOptions) -> list[RetrievalResult]:
        out: list[RetrievalResult] = []
        for row in rows:
            score = compute_final_score(
                bm25_score=row["bm25_score"], vector_score=None,
                updated_at=row["updated_at"], last_accessed_at=row["last_accessed_at"],
                access_count=row["access_count"] or 0,
                importance=row["importance"] or 0.5, confidence=row["confidence"] or 0.5,
                status=row["status"],
            )
            label = confidence_label(score.final_score)
            out.append(RetrievalResult(
                claim_id=row["claim_id"], content=row["content"],
                claim_type=row["claim_type"], status=row["status"],
                final_score=score.final_score, confidence_label=label,
                explanation=score_to_explanation(score) if opts.explain else {},
            ))
        return out

    def _record_retrieval_events(self, con: sqlite3.Connection, query: str, results: list[RetrievalResult], retriever: str) -> None:
        for index, result in enumerate(results):
            con.execute(
                "INSERT INTO retrieval_events(retrieval_id, query, claim_id, rank, final_score, confidence_label, retriever, explanation_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), query, result.claim_id, index + 1, result.final_score, result.confidence_label, retriever, json.dumps(result.explanation, ensure_ascii=False)),
            )

    def _reinforce_access(self, con: sqlite3.Connection, claim_ids: list[str]) -> None:
        now = utc_iso()
        for cid in claim_ids:
            con.execute("UPDATE claims SET access_count = COALESCE(access_count, 0) + 1, last_accessed_at = ? WHERE claim_id = ?", (now, cid))
