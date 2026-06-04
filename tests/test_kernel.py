"""Phase 1 kernel tests — evidence / claims / version history.

Aligns with Phase 1 specification.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from memoryx.core import MemoryKernel


@pytest.fixture
def kernel() -> MemoryKernel:
    db = str(Path(tempfile.mktemp(suffix=".db")))
    k = MemoryKernel(db)
    yield k
    k.close()
    Path(db).unlink(missing_ok=True)


# ------------------------------------------------------------------
# test_create_evidence_and_claim — full lifecycle
# ------------------------------------------------------------------

def test_create_evidence_and_claim(kernel: MemoryKernel) -> None:
    ev = kernel.create_evidence("user_message", "hello world", metadata={"k": "v"})

    # evidence persisted
    evidence = kernel.get_evidence(ev)
    assert evidence is not None
    assert evidence["content"] == "hello world"
    assert evidence["content_hash"]

    # claim created
    cid = kernel.create_claim(
        "fact", "hello world fact", [ev],
        confidence=0.7, importance=0.8,
    )
    claim = kernel.get_claim(cid)
    assert claim is not None
    assert claim["status"] == "active"
    assert claim["confidence"] == 0.7
    assert claim["importance"] == 0.8

    # version recorded
    versions = kernel.get_claim_versions(cid)
    assert len(versions) == 1
    assert versions[0]["operation"] == "create"
    # evidence_id should appear somewhere in the version
    assert ev in versions[0]["evidence_ids"] or ev in str(versions[0])


# ------------------------------------------------------------------
# test_revoke_claim_records_version
# ------------------------------------------------------------------

def test_revoke_claim_records_version(kernel: MemoryKernel) -> None:
    ev = kernel.create_evidence("user_message", "test")
    cid = kernel.create_claim("fact", "test fact", [ev])

    kernel.revoke_claim(cid, reason="user request")
    claim = kernel.get_claim(cid)
    assert claim["status"] == "revoked"

    versions = kernel.get_claim_versions(cid)
    assert len(versions) == 2
    assert versions[-1]["operation"] == "revoke"
    assert versions[-1]["reason"] == "user request"


# ------------------------------------------------------------------
# test_revoke_missing_claim_raises
# ------------------------------------------------------------------

def test_revoke_missing_claim_raises(kernel: MemoryKernel) -> None:
    with pytest.raises(ValueError, match="claim not found"):
        kernel.revoke_claim("nonexistent")


# ------------------------------------------------------------------
# test_list_claims_by_status
# ------------------------------------------------------------------

def test_list_claims_by_status(kernel: MemoryKernel) -> None:
    ev1 = kernel.create_evidence("user_message", "a")
    ev2 = kernel.create_evidence("user_message", "b")
    c1 = kernel.create_claim("fact", "a fact", [ev1])
    c2 = kernel.create_claim("fact", "b fact", [ev2])
    kernel.revoke_claim(c2)

    active = kernel.list_claims(status="active")
    revoked = kernel.list_claims(status="revoked")
    assert [c["claim_id"] for c in active] == [c1]
    assert [c["claim_id"] for c in revoked] == [c2]

    # No filter returns all
    all_claims = kernel.list_claims()
    assert len(all_claims) == 2