from memoryx.context_budget import ActiveRequestStore
from memoryx.core import MemoryKernel

def test_run_guard_rejects_stale_request(tmp_path):
    db = str(tmp_path / "m.db")
    MemoryKernel(db).close()
    guard = ActiveRequestStore(db)
    guard.begin_request(session_id="s", task_text="old", request_id="old")
    guard.begin_request(session_id="s", task_text="new", request_id="new")
    assert guard.reject_if_stale("old", "s")["error"] == "stale_result"
    assert guard.reject_if_stale("new", "s") is None
