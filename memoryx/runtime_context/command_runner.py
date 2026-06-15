from __future__ import annotations
import shlex
import subprocess
import time
import uuid
from typing import Any

from .artifacts import ArtifactStore
from .budget import RuntimeContextBudget
from .transcript import RuntimeTranscriptStore
from .truncate import summarize_terminal_output

class RuntimeCommandRunner:
    def __init__(self, db_path: str, *, artifact_root: str = ".memoryx/runtime_artifacts", budget: RuntimeContextBudget | None = None):
        self.db_path = db_path
        self.budget = budget or RuntimeContextBudget.from_env()
        self.artifacts = ArtifactStore(artifact_root)
        self.transcripts = RuntimeTranscriptStore(db_path, self.budget)

    def run(self, *, task_id: str, request_id: str, command: str, cwd: str | None = None, timeout: int | None = None, shell: bool = False, env: dict[str, str] | None = None) -> dict[str, Any]:
        if shell:
            raise ValueError("shell=True is not allowed for security reasons. Please use shell=False with properly escaped commands.")
        
        cmd_args = shlex.split(command)
        started = time.perf_counter()
        proc = subprocess.run(cmd_args, cwd=cwd, shell=False, capture_output=True, text=True, timeout=timeout, env=env)
        duration_ms = (time.perf_counter() - started) * 1000
        event_id = uuid.uuid4().hex
        stdout_ref = self.artifacts.write_text(kind="stdout", name=f"{event_id}.stdout.log", text=proc.stdout or "", summary=f"stdout for `{command}`; {len(proc.stdout or '')} chars") if proc.stdout else None
        stderr_ref = self.artifacts.write_text(kind="stderr", name=f"{event_id}.stderr.log", text=proc.stderr or "", summary=f"stderr for `{command}`; {len(proc.stderr or '')} chars") if proc.stderr else None
        self.transcripts.record_command(event_id=event_id, task_id=task_id, request_id=request_id, command=command, exit_code=proc.returncode, duration_ms=duration_ms, stdout=proc.stdout or "", stderr=proc.stderr or "")
        summary = summarize_terminal_output(proc.stdout or "", proc.stderr or "", max_stdout_chars=self.budget.max_command_stdout_chars, max_stderr_chars=self.budget.max_command_stderr_chars, max_lines=self.budget.max_terminal_lines)
        return {
            "ok": proc.returncode == 0, "prompt_safe": True, "event_id": event_id, "task_id": task_id, "request_id": request_id,
            "command": command, "cwd": cwd, "exit_code": proc.returncode, "duration_ms": duration_ms,
            "stdout_summary": summary["stdout"], "stderr_summary": summary["stderr"],
            "stdout_truncated": summary["stdout_truncated"], "stderr_truncated": summary["stderr_truncated"],
            "stdout_original_chars": summary["stdout_original_chars"], "stderr_original_chars": summary["stderr_original_chars"],
            "stdout_artifact": stdout_ref.to_dict() if stdout_ref else None, "stderr_artifact": stderr_ref.to_dict() if stderr_ref else None,
        }
