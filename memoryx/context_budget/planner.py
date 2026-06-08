from __future__ import annotations
from dataclasses import dataclass
import os, re
from .policy import ContextBudgetPolicy
from .profiles import ContextMode, clamp_profile_to_model_window, get_context_profile

DEEP_PATTERNS = [r"\barchitecture\b", r"\bmigration\b", r"\bdebug\b", r"\btrace\b",
                 r"\bperformance\b", r"\bbenchmark\b", r"\bphase\b", r"\bpatch\b",
                 r"\bimplementation\b", r"\brefactor\b", r"\broot cause\b",
                 r"\bregression\b", r"\bsecurity\b", r"\bconcurrency\b"]
BRIEF_PATTERNS = [r"\bquick\b", r"\bshort\b", r"\bbrief\b", r"\bsummary\b", r"\b一句话\b", r"\b简短\b"]
DEBUG_PATTERNS = [r"\braw\b", r"\bfull debug\b", r"\bexplain retrieval\b", r"\bdiagnostics\b", r"\braw_fts\b"]

@dataclass(frozen=True)
class ContextPlan:
    mode: ContextMode; reason: str; profile: ContextProfile; policy: ContextBudgetPolicy

class AdaptiveContextPlanner:
    def __init__(self, model_window_tokens: int | None = None):
        self.model_window_tokens = model_window_tokens or int(os.getenv("MEMORYX_MODEL_CONTEXT_TOKENS", "256000"))

    def plan(self, query: str, requested_mode: str | None = None) -> ContextPlan:
        q = query or ""
        if requested_mode: selected = requested_mode.lower(); reason = f"explicit mode={selected}"
        elif matches_any(q, DEBUG_PATTERNS): selected = "debug"; reason = "matched debug intent"
        elif matches_any(q, DEEP_PATTERNS): selected = "deep"; reason = "matched deep technical intent"
        elif matches_any(q, BRIEF_PATTERNS) or len(q) < 30: selected = "brief"; reason = "matched brief intent"
        else: selected = "standard"; reason = "default standard mode"

        profile = clamp_profile_to_model_window(get_context_profile(selected), self.model_window_tokens)
        policy = ContextBudgetPolicy(enabled=True, model_context_window_tokens=self.model_window_tokens,
            max_context_tokens=profile.max_context_tokens, max_memory_items=profile.max_memory_items,
            max_session_items=profile.max_session_items, max_item_tokens=profile.max_item_tokens,
            min_score=profile.min_score, include_explanations=profile.include_explanations, new_thread_carryover=False)
        return ContextPlan(profile.mode, reason, profile, policy)

def matches_any(text: str, patterns: list[str]) -> bool:
    lowered = text.lower()
    return any(re.search(pattern, lowered) for pattern in patterns)
