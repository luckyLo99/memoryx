from __future__ import annotations
from typing import Any
from .artifacts import ArtifactRef
from .budget import RuntimeContextBudget
from .capsule import TaskCapsule, TaskCapsuleStore
from .command_runner import RuntimeCommandRunner
from .guard import RuntimeTaskGuard
from .assembler import RuntimePromptAssembler
from .patch_guard import PatchArtifactGuard

class HermesRuntimeContext:
    def __init__(self, db_path: str, *, artifact_root: str = ".memoryx/runtime_artifacts", budget: RuntimeContextBudget | None = None):
        self.db_path = db_path
        self.budget = budget or RuntimeContextBudget.from_env()
        self.guard = RuntimeTaskGuard(db_path)
        self.commands = RuntimeCommandRunner(db_path, artifact_root=artifact_root, budget=self.budget)
        self.patches = PatchArtifactGuard(artifact_root=artifact_root, budget=self.budget)
        self.capsules = TaskCapsuleStore(db_path, self.budget)
        self.assembler = RuntimePromptAssembler(db_path, self.budget)
        self.artifact_refs: list[ArtifactRef] = []

    def begin_request(self, task_id: str, request_id: str) -> dict[str, Any]:
        lease = self.guard.begin(task_id, request_id)
        return {"ok": True, "lease": {"task_id": lease.task_id, "request_id": lease.request_id, "status": lease.status}}

    def upsert_capsule(self, capsule: TaskCapsule) -> dict[str, Any]:
        return {"ok": True, "capsule": self.capsules.upsert(capsule).to_dict()}

    def run_command(self, *, task_id: str, request_id: str, command: str, cwd: str | None = None, timeout: int | None = None) -> dict[str, Any]:
        stale = self.guard.reject_if_stale(task_id, request_id)
        if stale:
            return stale
        result = self.commands.run(task_id=task_id, request_id=request_id, command=command, cwd=cwd, timeout=timeout)
        for key in ["stdout_artifact", "stderr_artifact"]:
            a = result.get(key)
            if a:
                self.artifact_refs.append(ArtifactRef(artifact_id=a["artifact_id"], path=a["path"], kind=a["kind"], bytes=a["bytes"], sha256=a["sha256"], summary=a["summary"]))
        return result

    def store_patch(self, *, name: str, patch_text: str) -> dict[str, Any]:
        result = self.patches.store_patch(name=name, patch_text=patch_text)
        a = result.get("artifact")
        if a:
            self.artifact_refs.append(ArtifactRef(artifact_id=a["artifact_id"], path=a["path"], kind=a["kind"], bytes=a["bytes"], sha256=a["sha256"], summary=a["summary"]))
        return result

    def assemble_prompt(self, *, task_id: str, request_id: str) -> dict[str, Any]:
        stale = self.guard.reject_if_stale(task_id, request_id)
        if stale:
            return stale
        return self.assembler.assemble(task_id=task_id, request_id=request_id, artifact_refs=self.artifact_refs)

    def complete_request(self, request_id: str) -> None:
        self.guard.complete(request_id)
