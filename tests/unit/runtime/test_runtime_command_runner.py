from pathlib import Path
import pytest

from memoryx.runtime_context import RuntimeCommandRunner, RuntimeContextBudget


def test_command_runner_returns_prompt_safe_summary(tmp_path):
    db = str(tmp_path / "m.db")
    budget = RuntimeContextBudget(max_command_stdout_chars=1000, max_terminal_lines=20)
    runner = RuntimeCommandRunner(db, artifact_root=str(tmp_path / "artifacts"), budget=budget)

    cmd = "python -c \"print('X' * 200000)\""
    result = runner.run(
        task_id="t",
        request_id="r",
        command=cmd,
        cwd=str(tmp_path),
    )

    assert result["prompt_safe"] is True
    assert result["stdout_truncated"] is True
    assert result["stdout_original_chars"] >= 200000
    assert len(result["stdout_summary"]) < 2000
    assert result["stdout_artifact"] is not None
    assert Path(result["stdout_artifact"]["path"]).exists()


def test_command_runner_shell_true_raises_error(tmp_path):
    db = str(tmp_path / "m.db")
    runner = RuntimeCommandRunner(db, artifact_root=str(tmp_path / "artifacts"))

    cmd = "echo hello"
    with pytest.raises(ValueError, match="shell=True is not allowed"):
        runner.run(
            task_id="t",
            request_id="r",
            command=cmd,
            cwd=str(tmp_path),
            shell=True,
        )
