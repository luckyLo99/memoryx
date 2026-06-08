from __future__ import annotations

from dataclasses import asdict
from typing import Any
from memoryx.safety.context_isolation import wrap_untrusted_artifact, wrap_untrusted_session_context
from memoryx.safety.llm_firewall import LLMFirewall, safety_preamble
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
        self.firewall = LLMFirewall()
    def assemble(self, *, task_id: str, request_id: str, artifact_refs: list[ArtifactRef] | None = None, recent_tool_limit: int = 8) -> dict[str, Any]:
        capsule = self.capsules.get(task_id)
        events = self.transcripts.recent_events(task_id, limit=recent_tool_limit)
        artifact_refs = artifact_refs or []
        lines = ["# MemoryX Runtime Context", "", safety_preamble(), "", "## Active Request", f"- task_id: {task_id}", f"- request_id: {request_id}", ""]
        if capsule:
            lines.extend(["## Task Capsule", f"Objective: {capsule.objective}", "", "Constraints:"])
            lines.extend([self._wrap_session_line(x, record_id=f"{task_id}:constraint:{idx}", source="memoryx.task_capsule") for idx, x in enumerate(capsule.constraints)])
            lines.extend(["", "Completed steps:"] + [self._wrap_session_line(x, record_id=f"{task_id}:completed:{idx}", source="memoryx.task_capsule") for idx, x in enumerate(capsule.completed_steps[-20:])] + ["", "Current state:", self._wrap_session_line(capsule.current_state, record_id=f"{task_id}:current_state", source="memoryx.task_capsule"), "", "Next steps:"] + [self._wrap_session_line(x, record_id=f"{task_id}:next:{idx}", source="memoryx.task_capsule") for idx, x in enumerate(capsule.next_steps[:10])] + [""])
        if events:
            lines.append("## Recent Tool Events")
            for e in events:
                stdout_decision = self.firewall._inspect_text(e.stdout_summary, surface="tool_output")
                lines.extend([f"### command: {e.command}", f"- exit_code: {e.exit_code}", f"- duration_ms: {e.duration_ms:.2f}", f"- stdout_truncated: {e.stdout_truncated}", f"- stderr_truncated: {e.stderr_truncated}", "stdout:", self.firewall.wrap_untrusted_tool_output(e.stdout_summary, risk_flags=stdout_decision.flags)])
                if e.stderr_summary:
                    stderr_decision = self.firewall._inspect_text(e.stderr_summary, surface="tool_output")
                    lines.extend(["stderr:", self.firewall.wrap_untrusted_tool_output(e.stderr_summary, risk_flags=stderr_decision.flags)])
        if artifact_refs:
            lines.append("## Artifact References")
            for ref in artifact_refs:
                lines.extend([wrap_untrusted_artifact(
                    f"kind: {ref.kind}\npath: {ref.path}\nbytes: {ref.bytes}\nsha256: {ref.sha256}\nsummary: {ref.summary}",
                    record_id=ref.artifact_id,
                    source="memoryx.artifact_ref",
                    metadata={"kind": ref.kind, "bytes": ref.bytes, "sha256": ref.sha256},
                )])
        text = "\n".join(lines)
        self.budget.assert_prompt_budget(text)
        return {"ok": True, "task_id": task_id, "request_id": request_id, "estimated_tokens": self.budget.estimate_tokens(text), "text": text, "tool_event_count": len(events), "artifact_count": len(artifact_refs), "budget": asdict(self.budget)}

    def _wrap_session_line(self, text: str, *, record_id: str, source: str) -> str:
        decision = self.firewall.inspect_memory_context_sync(text)
        return wrap_untrusted_session_context(
            text,
            record_id=record_id,
            source=source,
            risk_flags=decision.flags,
        )
