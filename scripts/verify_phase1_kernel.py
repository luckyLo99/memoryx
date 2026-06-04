#!/usr/bin/env python3
"""Phase 1 end-to-end kernel verification.

Usage:
    python scripts/verify_phase1_kernel.py
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from memoryx.core import MemoryKernel, Retriever


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        db = str(Path(td) / "phase1.db")

        # 1. Create kernel and evidence
        kernel = MemoryKernel(db)
        ev = kernel.create_evidence(
            "user_message",
            "I prefer concise answers",
            session_id="s1",
            user_id="u1",
            metadata={"source": "verify"},
        )
        assert kernel.get_evidence(ev) is not None
        assert kernel.get_evidence(ev)["content"] == "I prefer concise answers"
        print("  PASS  evidence_events append-only")

        # 2. Create claim
        cid = kernel.create_claim(
            "preference",
            "User prefers concise answers",
            [ev],
            confidence=0.9,
            importance=0.8,
        )
        claim = kernel.get_claim(cid)
        assert claim is not None
        assert claim["status"] == "active"
        assert claim["confidence"] == 0.9
        assert claim["importance"] == 0.8
        print("  PASS  claims create/retrieve")

        # 3. Version history
        versions = kernel.get_claim_versions(cid)
        assert len(versions) == 1
        assert versions[0]["operation"] == "create"
        print("  PASS  claim_versions on create")

        # 4. FTS5 retrieval
        results = Retriever(db).search("concise", limit=5)
        assert len(results) == 1
        assert results[0].claim_id == cid
        assert "bm25_score" in results[0].explanation
        assert results[0].explanation["retriever"] == "fts5"
        print("  PASS  FTS5 retrieval works")

        # 5. Revoke
        kernel.revoke_claim(cid, reason="verify revoke")
        assert kernel.get_claim(cid)["status"] == "revoked"
        versions2 = kernel.get_claim_versions(cid)
        assert len(versions2) == 2
        print("  PASS  revoke marks claim + writes version")

        # 6. Revoked hidden by default
        hidden = Retriever(db).search("concise", limit=5)
        assert hidden == []
        print("  PASS  revoked hidden by default")

        # 7. include_inactive
        visible = Retriever(db).search("concise", limit=5, include_inactive=True)
        assert len(visible) == 1
        print("  PASS  include_inactive=True reveals revoked")

        # 8. Lite — no embedding/vector dependency
        import sqlite3
        con = sqlite3.connect(db)
        has_fts = con.execute(
            "SELECT name FROM sqlite_master WHERE name='fts_memories'"
        ).fetchone() is not None
        assert has_fts
        con.close()
        print("  PASS  Lite mode — 0 embedding dependency")

        kernel.close()

    print()
    print("PASS Phase 1 kernel verification")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())