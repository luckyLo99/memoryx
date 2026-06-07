from memoryx.runtime_context import RuntimeTaskGuard

def test_runtime_task_guard_rejects_stale(tmp_path):
    db = str(tmp_path / "m.db")
    guard = RuntimeTaskGuard(db)
    guard.begin("task", "old")
    guard.begin("task", "new")
    assert guard.reject_if_stale("task", "old")["error"] == "stale_runtime_result"
    assert guard.reject_if_stale("task", "new") is None
