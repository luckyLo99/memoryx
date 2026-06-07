from __future__ import annotations

from dataclasses import dataclass
import os

class RuntimeBudgetViolation(RuntimeError):
    pass

@dataclass(frozen=True)
class RuntimeContextBudget:
    max_prompt_tokens: int = 1_000_000
    max_task_capsule_tokens: int = 12_000
    max_tool_summary_tokens: int = 8_000
    max_artifact_ref_tokens: int = 2_000
    max_terminal_output_chars: int = 12_000
    max_terminal_lines: int = 120
    max_command_stdout_chars: int = 8_000
    max_command_stderr_chars: int = 4_000
    max_inline_patch_chars: int = 0
    artifact_only_patches: bool = True
    reject_stale_task_results: bool = True

    @classmethod
    def from_env(cls) -> "RuntimeContextBudget":
        return cls(
            max_prompt_tokens=int(os.getenv("MEMORYX_RUNTIME_MAX_PROMPT_TOKENS", "1000000")),
            max_task_capsule_tokens=int(os.getenv("MEMORYX_RUNTIME_MAX_TASK_CAPSULE_TOKENS", "12000")),
            max_tool_summary_tokens=int(os.getenv("MEMORYX_RUNTIME_MAX_TOOL_SUMMARY_TOKENS", "8000")),
            max_artifact_ref_tokens=int(os.getenv("MEMORYX_RUNTIME_MAX_ARTIFACT_REF_TOKENS", "2000")),
            max_terminal_output_chars=int(os.getenv("MEMORYX_RUNTIME_MAX_TERMINAL_CHARS", "12000")),
            max_terminal_lines=int(os.getenv("MEMORYX_RUNTIME_MAX_TERMINAL_LINES", "120")),
            max_command_stdout_chars=int(os.getenv("MEMORYX_RUNTIME_MAX_STDOUT_CHARS", "8000")),
            max_command_stderr_chars=int(os.getenv("MEMORYX_RUNTIME_MAX_STDERR_CHARS", "4000")),
            max_inline_patch_chars=int(os.getenv("MEMORYX_RUNTIME_MAX_INLINE_PATCH_CHARS", "0")),
            artifact_only_patches=os.getenv("MEMORYX_RUNTIME_ARTIFACT_ONLY_PATCHES", "true").lower() == "true",
            reject_stale_task_results=os.getenv("MEMORYX_RUNTIME_REJECT_STALE_RESULTS", "true").lower() == "true",
        )

    def estimate_tokens(self, text: str) -> int:
        return max(1, int(len(text or "") / 4) + 1)

    def assert_prompt_budget(self, text: str) -> None:
        tokens = self.estimate_tokens(text)
        if tokens > self.max_prompt_tokens:
            raise RuntimeBudgetViolation(
                f"runtime prompt budget exceeded: {tokens} > {self.max_prompt_tokens}"
            )
