from __future__ import annotations
from pathlib import Path
import tempfile
from memoryx.core import MemoryKernel, SearchOptions
from memoryx.core.hybrid_retriever import HybridRetriever
from memoryx.core.vector import NullVectorProvider, VectorHit

class FakeVectorProvider:
    available = True
    def __init__(self, hits): self.hits = hits
    def search(self, query, limit=20): return self.hits[:limit]
    def upsert(self, claim_id, content): pass
    def delete(self, claim_id): pass

def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        db = str(Path(td) / "phase2.db")
        kernel = MemoryKernel(db)

        ev = kernel.create_evidence("user_message", "I prefer concise answers")
        c1 = kernel.create_claim("preference", "User prefers concise answers", [ev], confidence=0.9, importance=0.8)

        # 1. Lite scoring
        from memoryx.core.retriever import Retriever
        hits = Retriever(db).search("concise", options=SearchOptions(limit=5))
        assert hits, "scoring should return results"
        assert "lexical_score" in hits[0].explanation, "explanation with breakdown"
        print("  PASS  Lite scoring + explanation")

        # 2. Access reinforcement
        ac = kernel.get_claim(c1)["access_count"]
        assert ac >= 1, f"access_count >= 1, got {ac}"
        print("  PASS  access reinforcement")

        # 3. Supersede
        ev2 = kernel.create_evidence("user_message", "I now prefer detailed answers")
        c2 = kernel.supersede_claim(c1, "preference", "User prefers detailed answers", [ev2], reason="updated")
        assert kernel.get_claim(c1)["status"] == "superseded"
        assert kernel.get_claim(c1)["superseded_by"] == c2
        print("  PASS  supersede governance")

        # 4. Hybrid RRF
        fake = FakeVectorProvider([VectorHit(c2, 0.99)])
        hybrid = HybridRetriever(db, fake)
        hh = hybrid.search("verbose style", options=SearchOptions(mode="hybrid", limit=5, min_score=0.0))
        assert hh, "hybrid should return results"
        assert hh[0].explanation["fusion"]["method"] == "rrf"
        print("  PASS  hybrid RRF fusion")

        # 5. Conflict + resolve
        c3 = kernel.create_claim("preference", "short answers", [ev], confidence=0.6, importance=0.6)
        group = kernel.mark_conflict(c2, c3)
        kernel.resolve_conflict(group, c2)
        assert kernel.get_claim(c2)["status"] == "active"
        assert kernel.get_claim(c3)["status"] == "superseded"
        print("  PASS  conflict governance")

        # 6. Lite mode — 0 embedding
        from memoryx.core.vector import NullVectorProvider
        nv = NullVectorProvider()
        assert not nv.available
        assert nv.search("x") == []
        print("  PASS  Lite mode — 0 embedding dependency")

        # 7. retrieval_events exist
        cnt = kernel.conn.execute("SELECT count(*) FROM retrieval_events").fetchone()[0]
        assert cnt >= 1, f"retrieval_events count >= 1, got {cnt}"
        print("  PASS  retrieval_events logged")

        # 8. Revoked hidden
        kernel.revoke_claim(c3)
        hidden = Retriever(db).search("short", options=SearchOptions(limit=5))
        assert not any(r.claim_id == c3 for r in hidden), "revoked hidden"
        visible = Retriever(db).search("short", options=SearchOptions(limit=5, include_inactive=True, min_score=0.0, reject_low_confidence=False))
        assert any(r.claim_id == c3 for r in visible), "include_inactive reveals"
        print("  PASS  revoked hidden by default")

        kernel.close()

    print()
    print("PASS Phase 2 kernel verification")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
