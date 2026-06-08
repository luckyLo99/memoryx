from __future__ import annotations

from dataclasses import dataclass, asdict
import json
from pathlib import Path
from typing import Any

@dataclass(frozen=True)
class HermesContextPolicy:
    disable_session_search: bool = True
    disable_auto_recall: bool = True
    disable_raw_terminal_injection: bool = True
    disable_raw_patch_injection: bool = True
    require_runtime_prompt_assembler: bool = True
    max_active_context_tokens: int = 64_000
    max_reasoning_history_tokens: int = 8_000
    max_tool_result_tokens: int = 8_000
    max_recall_items: int = 0
    artifact_only_patches: bool = True
    fail_fast_on_budget_violation: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_system_instructions(self) -> str:
        return """Hermes Runtime Context Policy:

- Do not call session_search unless the user explicitly asks.
- Do not recall previous conversation history by default.
- Do not inject raw terminal stdout/stderr into the model context.
- Do not inline patches or diffs; store them as artifact references.
- Use RuntimePromptAssembler for runtime context.
- Use RuntimeCommandRunner for shell commands.
- If active context would exceed 64k tokens, stop and report budget_violation.
- Treat old task results as stale unless request_id matches the active task.
"""

def write_policy_files(root: str = ".") -> dict[str, str]:
    base = Path(root)
    policy = HermesContextPolicy()
    json_path = base / "hermes_context_policy.json"
    txt_path = base / "HERMES_CONTEXT_POLICY.md"
    json_path.write_text(json.dumps(policy.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    txt_path.write_text("# Hermes Context Policy\n\n" + policy.to_system_instructions(), encoding="utf-8")
    return {"json": str(json_path), "markdown": str(txt_path)}
