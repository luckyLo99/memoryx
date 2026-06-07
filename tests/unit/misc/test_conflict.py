from memoryx.core import MemoryKernel

def test_supersede_claim(tmp_path):
    db = str(tmp_path / "m.db")
    k = MemoryKernel(db)
    ev1 = k.create_evidence("user_message", "short")
    old = k.create_claim("preference", "short", [ev1])
    ev2 = k.create_evidence("user_message", "long")
    new = k.supersede_claim(old, "preference", "long", [ev2])
    assert k.get_claim(old)["status"] == "superseded"
    assert k.get_claim(old)["superseded_by"] == new
    assert k.get_claim(new)["status"] == "active"

def test_conflict_resolution(tmp_path):
    db = str(tmp_path / "m.db")
    k = MemoryKernel(db)
    a = k.create_claim("preference", "a", [k.create_evidence("user_message", "a")])
    b = k.create_claim("preference", "b", [k.create_evidence("user_message", "b")])
    group = k.mark_conflict(a, b)
    assert k.get_claim(a)["status"] == "conflicted"
    assert k.get_claim(b)["status"] == "conflicted"
    k.resolve_conflict(group, b)
    assert k.get_claim(b)["status"] == "active"
    assert k.get_claim(a)["status"] == "superseded"

def test_reinforce_claim(tmp_path):
    db = str(tmp_path / "m.db")
    k = MemoryKernel(db)
    cid = k.create_claim("fact", "data", [], confidence=0.5, importance=0.5)
    k.reinforce_claim(cid)
    c = k.get_claim(cid)
    assert c["confidence"] > 0.5

def test_update_claim_content(tmp_path):
    db = str(tmp_path / "m.db")
    k = MemoryKernel(db)
    cid = k.create_claim("fact", "old content", [])
    k.update_claim(cid, content="new content")
    assert k.get_claim(cid)["content"] == "new content"
