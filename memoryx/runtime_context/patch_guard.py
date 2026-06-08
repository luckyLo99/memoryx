from __future__ import annotations
from pathlib import Path
from typing import Any
from .artifacts import ArtifactStore
from .budget import RuntimeContextBudget

class PatchArtifactGuard:
    def __init__(self, artifact_root: str = ".memoryx/runtime_artifacts", budget: RuntimeContextBudget | None = None):
        self.artifacts = ArtifactStore(artifact_root)
        self.budget = budget or RuntimeContextBudget.from_env()

    def store_patch(self, *, name: str, patch_text: str, kind: str = "patch") -> dict[str, Any]:
        if not self.budget.artifact_only_patches and len(patch_text) <= self.budget.max_inline_patch_chars:
            return {"prompt_safe": True, "inline_allowed": True, "patch_text": patch_text, "artifact": None}
        ref = self.artifacts.write_text(kind=kind, name=name, text=patch_text, summary=self._summarize_patch(patch_text))
        return {"prompt_safe": True, "inline_allowed": False, "patch_text": "", "artifact": ref.to_dict()}

    def _summarize_patch(self, text: str) -> str:
        lines = (text or "").splitlines()
        files = sum(1 for x in lines if x.startswith("diff --git"))
        added = sum(1 for x in lines if x.startswith("+") and not x.startswith("+++"))
        removed = sum(1 for x in lines if x.startswith("-") and not x.startswith("---"))
        return f"{files} files, +{added}/-{removed}, {len(lines)} lines"
