from __future__ import annotations
from pathlib import Path
import tempfile
import uuid
from memoryx.runtime_context import ArtifactStore, RuntimeContextBudget, RuntimePromptAssembler, RuntimeTaskGuard, RuntimeTranscriptStore, TaskCapsule, TaskCapsuleStore

def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        db = str(root / "runtime_context.db")
        budget = RuntimeContextBudget(max_prompt_tokens=16000, max_task_capsule_tokens=4000, max_tool_summary_tokens=4000, max_artifact_ref_tokens=2000, max_terminal_output_chars=4000, max_terminal_lines=40, max_command_stdout_chars=3000, max_command_stderr_chars=1000, max_inline_patch_chars=0, artifact_only_patches=True)
        task_id, old_req, new_req = "task-context-firewall", "old-request", "new-request"
        guard = RuntimeTaskGuard(db)
        guard.begin(task_id, old_req)
        guard.begin(task_id, new_req)
        assert guard.reject_if_stale(task_id, old_req)["error"] == "stale_runtime_result"
        TaskCapsuleStore(db, budget).upsert(TaskCapsule(task_id=task_id, objective="Fix runtime context bloat", constraints=["Do not inline full patch.", "Do not inline full terminal logs.", "Keep active context under budget."], completed_steps=[], current_state="testing", next_steps=[], updated_at="now"))
        huge_stdout = "\n".join(f"line {i} " + ("X" * 200) for i in range(5000))
        store = RuntimeTranscriptStore(db, budget)
        event = store.record_command(event_id=uuid.uuid4().hex, task_id=task_id, request_id=new_req, command="pytest -q", exit_code=0, duration_ms=1234.5, stdout=huge_stdout)
        assert event.stdout_truncated is True
        patch_text = "\n".join(f"+ line {i}" for i in range(20000))
        artifacts = ArtifactStore(str(root / "artifacts"))
        patch_ref = artifacts.write_text(kind="patch", name="phase15_8.patch", text=patch_text, summary="large patch stored as artifact ref only")
        assert patch_ref.bytes > 100000
        runtime = RuntimePromptAssembler(db, budget)
        assembled = runtime.assemble(task_id=task_id, request_id=new_req, artifact_refs=[patch_ref])
        assert assembled["ok"] is True
        assert assembled["estimated_tokens"] <= budget.max_prompt_tokens
        assert "large patch stored as artifact ref only" in assembled["text"]
        assert "truncated" in assembled["text"].lower()
    print("PASS Phase 15.8 runtime context firewall verification")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
