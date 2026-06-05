from __future__ import annotations
from dataclasses import dataclass
import os

@dataclass(frozen=True)
class ContextBudgetPolicy:
    enabled: bool = True
    model_context_window_tokens: int = 256_000
    max_context_tokens: int = 8_192
    max_context_ratio: float = 0.04
    max_memory_items: int = 24
    max_session_items: int = 8
    max_item_tokens: int = 512
    min_score: float = 0.20
    include_explanations: bool = False
    new_thread_carryover: bool = False
    stale_result_action: str = "reject"

    @classmethod
    def from_env(cls) -> "ContextBudgetPolicy":
        model_window = int(os.getenv("MEMORYX_MODEL_CONTEXT_TOKENS", "256000"))
        max_context = int(os.getenv("MEMORYX_CONTEXT_MAX_TOKENS", "8192"))
        ratio = float(os.getenv("MEMORYX_CONTEXT_MAX_RATIO", "0.04"))
        computed_cap = int(model_window * ratio)
        effective_max = min(max_context, computed_cap) if computed_cap > 0 else max_context
        return cls(
            enabled=os.getenv("MEMORYX_CONTEXT_MODE", "budgeted").lower() != "legacy",
            model_context_window_tokens=model_window,
            max_context_tokens=max(1024, effective_max),
            max_context_ratio=ratio,
            max_memory_items=int(os.getenv("MEMORYX_CONTEXT_MAX_ITEMS", "24")),
            max_session_items=int(os.getenv("MEMORYX_CONTEXT_MAX_SESSION_ITEMS", "8")),
            max_item_tokens=int(os.getenv("MEMORYX_CONTEXT_MAX_ITEM_TOKENS", "512")),
            min_score=float(os.getenv("MEMORYX_CONTEXT_MIN_SCORE", "0.20")),
            include_explanations=os.getenv("MEMORYX_CONTEXT_INCLUDE_EXPLANATIONS", "false").lower() == "true",
            new_thread_carryover=os.getenv("MEMORYX_CONTEXT_SESSION_CARRYOVER", "false").lower() == "true",
            stale_result_action=os.getenv("MEMORYX_REQUEST_STALE_ACTION", "reject").lower(),
        )
    def memory_budget_tokens(self) -> int:
        return self.max_context_tokens
    def section_budget(self, section: str) -> int:
        budgets = {"task_focus": int(self.max_context_tokens * 0.10), "relevant_memories": int(self.max_context_tokens * 0.65), "session_context": int(self.max_context_tokens * 0.15), "metadata": int(self.max_context_tokens * 0.10)}
        return max(128, budgets.get(section, int(self.max_context_tokens * 0.10)))
