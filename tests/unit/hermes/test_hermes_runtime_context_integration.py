from memoryx.runtime_context import HermesRuntimeContext, RuntimeContextBudget, TaskCapsule


def test_hermes_runtime_context_blocks_large_outputs(tmp_path):
    db = str(tmp_path / "m.db")
    runtime = HermesRuntimeContext(
        db,
        artifact_root=str(tmp_path / "artifacts"),
        budget=RuntimeContextBudget(max_prompt_tokens=64000, max_command_stdout_chars=1000, max_terminal_lines=20),
    )

    task_id = "t"
    request_id = "r"
    runtime.begin_request(task_id, request_id)
    runtime.upsert_capsule(TaskCapsule(
        task_id=task_id,
        objective="test",
        constraints=["bounded"],
        completed_steps=[],
        current_state="running",
        next_steps=[],
        updated_at="now",
    ))

    result = runtime.run_command(
        task_id=task_id,
        request_id=request_id,
        command="python3 -c \"print('Y' * 300000)\"",
        cwd=str(tmp_path),
    )
    assert result["prompt_safe"] is True
    assert result["stdout_truncated"] is True

    patch = runtime.store_patch(name="x.patch", patch_text="\n".join("+ p" for _ in range(10000)))
    assert patch["patch_text"] == ""

    prompt = runtime.assemble_prompt(task_id=task_id, request_id=request_id)
    assert prompt["ok"] is True
    assert prompt["estimated_tokens"] < 64000
    assert "Artifact References" in prompt["text"]


def test_hermes_runtime_context_rejects_stale(tmp_path):
    db = str(tmp_path / "m.db")
    runtime = HermesRuntimeContext(db, artifact_root=str(tmp_path / "artifacts"))

    runtime.begin_request("task", "old")
    runtime.begin_request("task", "new")

    result = runtime.run_command(
        task_id="task",
        request_id="old",
        command="python3 -c 'print(1)'",
        cwd=str(tmp_path),
    )

    assert result["error"] == "stale_runtime_result"
