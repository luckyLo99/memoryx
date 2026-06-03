"""Retriever — FTS5 keyword search with explainable scores."""

import sqlite3

from .types import RetrievalResult


class Retriever:
    """FTS5-based keyword retriever.

    Uses SQLite's built-in bm25() ranking function for ordering.
    The explanation dict includes the original query and raw FTS score
    so downstream consumers can interpret the ranking.
    """

    def __init__(self, db: str) -> None:
        self.db = db

    def search(self, query: str, limit: int = 10) -> list[RetrievalResult]:
        """Full-text search over claims.

        Returns results ordered by BM25 relevance (lower = better match).
        Each result includes a structured explanation for score transparency.
        """
        con = sqlite3.connect(self.db)
        cur = con.cursor()
        try:
            cur.execute(
                """SELECT claim_id, content, bm25(fts_memories) AS score
                   FROM fts_memories
                   WHERE fts_memories MATCH ?
                   ORDER BY score
                   LIMIT ?""",
                (query, limit),
            )
            rows = cur.fetchall()
        except sqlite3.OperationalError as e:
            # Return empty results on malformed FTS queries
            return []

        results: list[RetrievalResult] = []
        for cid, content, score in rows:
            results.append(RetrievalResult(
                claim_id=cid,
                content=content,
                score=score,
                explanation={
                    "matched": True,
                    "query": query,
                    "bm25_score": score,
                    "ranking_note": "lower BM25 = better match",
                },
            ))
        return results

    def count(self, query: str) -> int:
        """Return the number of matching results for a given query."""
        con = sqlite3.connect(self.db)
        cur = con.cursor()
        try:
            cur.execute(
                "SELECT count(*) FROM fts_memories WHERE fts_memories MATCH ?",
                (query,),
            )
            row = cur.fetchone()
            return row[0] if row else 0
        except sqlite3.OperationalError:
            return 0
