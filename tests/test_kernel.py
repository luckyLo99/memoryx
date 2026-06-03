"""Tests for the MemoryKernel — evidence, claims, version history."""

import os
import tempfile
import pytest

from memoryx.core.kernel import MemoryKernel


@pytest.fixture
def kernel():
    """Provide a MemoryKernel backed by a temporary DB."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    k = MemoryKernel(tmp.name)
    yield k
    k.close()
    os.unlink(tmp.name)


# ------------------------------------------------------------------
# Evidence
# ------------------------------------------------------------------

class TestEvidence:
    def test_create_evidence(self, kernel: MemoryKernel):
        ev_id = kernel.create_evidence("user", "我喜欢简洁回答")
        assert ev_id is not None
        assert len(ev_id) == 36  # UUID v4

    def test_create_evidence_with_metadata(self, kernel: MemoryKernel):
        ev_id = kernel.create_evidence(
            "assistant", "Here is a summary.",
            metadata={"session": "abc", "tokens": 150},
        )
        row = kernel.conn.execute(
            "SELECT source_type, content FROM evidence_events WHERE evidence_id = ?",
            (ev_id,),
        ).fetchone()
        assert row[0] == "assistant"
        assert "summary" in row[1]

    def test_multiple_evidence(self, kernel: MemoryKernel):
        e1 = kernel.create_evidence("user", "msg one")
        e2 = kernel.create_evidence("user", "msg two")
        count = kernel.conn.execute(
            "SELECT count(*) FROM evidence_events",
        ).fetchone()[0]
        assert count == 2


# ------------------------------------------------------------------
# Claims
# ------------------------------------------------------------------

class TestClaims:
    def test_create_claim(self, kernel: MemoryKernel):
        ev = kernel.create_evidence("user", "prefer concise")
        cid = kernel.create_claim("preference", "User prefers concise answers", [ev])
        claim = kernel.get_claim(cid)
        assert claim["status"] == "active"
        assert claim["claim_type"] == "preference"
        assert claim["content"] == "User prefers concise answers"
        assert claim["confidence"] == 0.5

    def test_create_claim_custom_confidence(self, kernel: MemoryKernel):
        cid = kernel.create_claim("fact", "important note", confidence=0.9, importance=0.8)
        claim = kernel.get_claim(cid)
        assert claim["confidence"] == 0.9
        assert claim["importance"] == 0.8

    def test_get_claim_not_found(self, kernel: MemoryKernel):
        assert kernel.get_claim("nonexistent") is None

    def test_create_claim_fts_index(self, kernel: MemoryKernel):
        cid = kernel.create_claim("fact", "Paris is the capital of France", [])
        row = kernel.conn.execute(
            "SELECT content FROM fts_memories WHERE claim_id = ?",
            (cid,),
        ).fetchone()
        assert row is not None
        assert "Paris" in row[0]


# ------------------------------------------------------------------
# Revoke & Supersede
# ------------------------------------------------------------------

class TestLifecycle:
    def test_revoke_claim(self, kernel: MemoryKernel):
        cid = kernel.create_claim("fact", "old info", [])
        kernel.revoke_claim(cid, "outdated")
        claim = kernel.get_claim(cid)
        assert claim["status"] == "revoked"

    def test_revoke_nonexistent_raises(self, kernel: MemoryKernel):
        with pytest.raises(ValueError, match="not found"):
            kernel.revoke_claim("nope")

    def test_supersede_claim(self, kernel: MemoryKernel):
        old = kernel.create_claim("preference", "old preference", [])
        new = kernel.create_claim("preference", "new preference", [])
        kernel.supersede_claim(old, new, "updated")
        claim = kernel.get_claim(old)
        assert claim["status"] == "superseded"


# ------------------------------------------------------------------
# Version history
# ------------------------------------------------------------------

class TestVersionHistory:
    def test_create_version(self, kernel: MemoryKernel):
        cid = kernel.create_claim("fact", "version test", [])
        versions = kernel.list_versions(cid)
        assert len(versions) == 1
        assert versions[0]["operation"] == "create"

    def test_revoke_version(self, kernel: MemoryKernel):
        cid = kernel.create_claim("fact", "to revoke", [])
        kernel.revoke_claim(cid, "test reason")
        versions = kernel.list_versions(cid)
        assert len(versions) == 2
        assert versions[0]["operation"] == "create"
        assert versions[1]["operation"] == "revoke"
        assert versions[1]["reason"] == "test reason"

    def test_supersede_version(self, kernel: MemoryKernel):
        old = kernel.create_claim("fact", "original", [])
        new = kernel.create_claim("fact", "replacement", [])
        kernel.supersede_claim(old, new, "better version")
        versions = kernel.list_versions(old)
        # create + supersede + the extra create for new claim? No, only old's versions
        assert len(versions) == 2
        assert versions[1]["operation"] == "supersede"
