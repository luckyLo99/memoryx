from __future__ import annotations

from dataclasses import asdict
from typing import Any
from .artifacts import ArtifactRef
from .budget import RuntimeContextBudget
from .capsule import TaskCapsuleStore
from .transcript import RuntimeTranscriptStore

class RuntimePromptAssembler:
    def __init__(self, db_path: str, budget: RuntimeContextBudget | None = None):
        self.db_path = db_path
        self.budget = budget or RuntimeContextBudget.from_env()
        self.capsules = TaskCapsuleStore(db_path, self.budget)
        self.transcripts = RuntimeTranscriptStore(db_path, self.budget)
    def assemble(self, *, task_id: str, request_id: str, artifact_refs: list[ArtifactRef] | None = None, recent_tool_limit: int = 8) -> dict[str, Any]:
        capsule = self.capsules.get(task_id)
        events = self.transcripts.recent_events(task_id, limit=recent_tool_limit)
        artifact_refs = artifact_refs or []
        lines = ["# MemoryX Runtime Context", "", "## Active Request", f"- task_id: {task_id}", f"- request_id: {request_id}", ""]
        if capsule:
            lines.extend(["## Task Capsule", f"Objective: {capsule.objective}", "", "Constraints:"])
            lines.extend([f"- {x}" for x in capsule.constraints])
            lines.extend(["", "Completed steps:"] + [f"- {x}" for x in capsule.completed_steps[-20:]] + ["", "Current state:", capsule.current_state, "", "Next steps:"] + [f"- {x}" for x in capsule.next_steps[:10]] + [""])
        if events:
            lines.append("## Recent Tool Events")
            for e in events:
                lines.extend([f"### command: {e.command}", f"- exit_code: {e.exit_code}", f"- duration_ms: {e.duration_ms:.2f}", f"- stdout_truncated: {e.stdout_truncated}", f"- stderr_truncated: {e.stderr_truncated}", "stdout:", "```", e.stdout_summary, "```"])
                if e.stderr_summary:
                    lines.extend(["stderr:", "```", e.stderr_summary, "```"])
        if artifact_refs:
            lines.append("## Artifact References")
            for ref in artifact_refs:
                lines.extend([f"- artifact_id: {ref.artifact_id}", f"  kind: {ref.kind}", f"  path: {ref.path}", f"  bytes: {ref.bytes}", f"  sha256: {ref.sha256}", f"  summary: {ref.summary}"])
        text = "\n".join(lines)
        self.budget.assert_prompt_budget(text)
        return {"ok": True, "task_id": task_id, "request_id": request_id, "estimated_tokens": self.budget.estimate_tokens(text), "text": text, "tool_event_count": len(events), "artifact_count": len(artifact_refs), "budget": asdict(self.budget)}
