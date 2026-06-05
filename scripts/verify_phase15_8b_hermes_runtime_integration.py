from __future__ import annotations

from pathlib import Path
import tempfile

from memoryx.runtime_context import HermesRuntimeContext, RuntimeContextBudget, TaskCapsule


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        db = str(root / "hermes_runtime.db")
        artifacts = str(root / "artifacts")

        budget = RuntimeContextBudget(
            max_prompt_tokens=64000,
            max_command_stdout_chars=8000,
            max_command_stderr_chars=4000,
            max_terminal_lines=120,
            max_inline_patch_chars=0,
            artifact_only_patches=True,
        )

        runtime = HermesRuntimeContext(db, artifact_root=artifacts, budget=budget)
        task_id = "hermes-runtime-lockdown"
        old_request = "old"
        request_id = "new"

        runtime.begin_request(task_id, old_request)
        runtime.begin_request(task_id, request_id)

        stale = runtime.run_command(
            task_id=task_id,
            request_id=old_request,
            command="python3 -c 'print(123)'",
        )
        assert stale["error"] == "stale_runtime_result", f"expected stale, got {stale}"

        runtime.upsert_capsule(
            TaskCapsule(
                task_id=task_id,
                objective="Verify Hermes runtime never returns full terminal output.",
                constraints=[
                    "No raw stdout in prompt",
                    "Patch artifact-only",
                    "Keep prompt under 64k tokens",
                ],
                completed_steps=[],
                current_state="Testing command wrapper integration",
                next_steps=["Run huge output commands", "Assemble prompt"],
                updated_at="now",
            )
        )

        # 360k repro: 1,440,000 chars stdout
        result = runtime.run_command(
            task_id=task_id,
            request_id=request_id,
            command="python3 -c \"print('X' * 1440000)\"",
            cwd=str(root),
            timeout=30,
        )

        assert result["prompt_safe"] is True, f"not prompt_safe: {result}"
        assert result["stdout_truncated"] is True, "stdout should be truncated"
        assert result["stdout_original_chars"] >= 1_440_000, f"too few chars: {result['stdout_original_chars']}"
        assert result["stdout_artifact"] is not None, "stdout artifact missing"
        assert len(result["stdout_summary"]) < 12000, f"summary too large: {len(result['stdout_summary'])}"

        print("360k repro PASS:")
        print(f"  stdout_original_chars: {result['stdout_original_chars']}")
        print(f"  stdout_summary chars: {len(result['stdout_summary'])}")
        print(f"  stdout_artifact: {result['stdout_artifact']['path']}")

        # Patch artifact-only: 100K+ lines, must NOT inline
        patch_text = "\n".join(f"+ patch line {i}" for i in range(100000))
        patch = runtime.store_patch(name="huge.patch", patch_text=patch_text)
        assert patch["prompt_safe"] is True
        assert patch["inline_allowed"] is False, "large patch should be artifact-only"
        assert patch["patch_text"] == "", "patch_text should be empty when artifact-only"
        assert patch["artifact"] is not None
        assert patch["artifact"]["bytes"] > 100000, f"artifact too small: {patch['artifact']['bytes']}"

        # Assemble prompt: must be <64k tokens
        assembled = runtime.assemble_prompt(task_id=task_id, request_id=request_id)
        assert assembled["ok"] is True
        assert assembled["estimated_tokens"] < 64000, f"too many tokens: {assembled['estimated_tokens']}"
        assert "Artifact References" in assembled["text"], "Artifact References missing"
        assert "patch line 99999" not in assembled["text"], "patch leaked into prompt"
        assert "truncated" in assembled["text"].lower(), "truncated marker missing"

        print(f"assembled prompt:")
        print(f"  estimated_tokens: {assembled['estimated_tokens']}")
        print(f"  output chars: {len(assembled['text'])}")
        print(f"  below 64k: {assembled['estimated_tokens'] < 64000}")
        print(f"  truncated marker: {'truncated' in assembled['text'].lower()}")
        print(f"  Artifact References: {'Artifact References' in assembled['text']}")

    print("\nPASS Phase 15.8B Hermes runtime integration verification")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
