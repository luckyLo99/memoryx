from pathlib import Path
from memoryx.runtime_context import ArtifactStore, RuntimeContextBudget, RuntimePromptAssembler, RuntimeTranscriptStore, TaskCapsule, TaskCapsuleStore

def test_runtime_prompt_assembler_uses_artifact_refs_not_full_patch(tmp_path):
    db = str(tmp_path / "m.db")
    budget = RuntimeContextBudget(max_prompt_tokens=12000, max_command_stdout_chars=1000, max_terminal_lines=20)
    task_id, request_id = "t", "r"
    TaskCapsuleStore(db, budget).upsert(TaskCapsule(task_id=task_id, objective="test", constraints=["no full patch"], completed_steps=[], current_state="running", next_steps=[], updated_at="now"))
    RuntimeTranscriptStore(db, budget).record_command(event_id="e", task_id=task_id, request_id=request_id, command="pytest", exit_code=0, duration_ms=1, stdout="\n".join("stdout" * 100 for _ in range(1000)))
    patch_ = "\n".join("+ secret patch line" for _ in range(10000))
    ref = ArtifactStore(str(tmp_path / "artifacts")).write_text(kind="patch", name="big.patch", text=patch_, summary="patch artifact")
    out = RuntimePromptAssembler(db, budget).assemble(task_id=task_id, request_id=request_id, artifact_refs=[ref])
    assert out["ok"]
    assert out["estimated_tokens"] <= budget.max_prompt_tokens
    assert "patch artifact" in out["text"]
    assert "+ secret patch line\n+ secret patch line\n+ secret patch line" not in out["text"]
