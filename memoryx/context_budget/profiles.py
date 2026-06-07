from __future__ import annotations
from dataclasses import dataclass
from typing import Literal

ContextMode = Literal["tiny", "brief", "standard", "deep", "debug", "ultra"]

@dataclass(frozen=True)
class ContextProfile:
    mode: ContextMode
    max_context_tokens: int
    max_memory_items: int
    max_session_items: int
    max_item_tokens: int
    min_score: float
    include_explanations: bool = False
    include_session_summary: bool = True
    omit_repeated_items: bool = True

CONTEXT_PROFILES: dict[str, ContextProfile] = {
    "tiny": ContextProfile("tiny", 2048, 6, 2, 192, 0.30),
    "brief": ContextProfile("brief", 4096, 12, 3, 256, 0.25),
    "standard": ContextProfile("standard", 8192, 24, 4, 512, 0.20),
    "deep": ContextProfile("deep", 16384, 48, 6, 768, 0.12),
    "debug": ContextProfile("debug", 32768, 96, 8, 1024, 0.0, include_explanations=True, omit_repeated_items=False),
    "ultra": ContextProfile("ultra", 100000, 200, 20, 2048, 0.10),
}

def get_context_profile(mode: str | None = None) -> ContextProfile:
    key = (mode or "standard").lower()
    return CONTEXT_PROFILES.get(key, CONTEXT_PROFILES["standard"])

def clamp_profile_to_model_window(profile: ContextProfile, model_window_tokens: int) -> ContextProfile:
    cap = max(1024, int(model_window_tokens * 0.20))
    max_tokens = min(profile.max_context_tokens, cap)
    return ContextProfile(profile.mode, max_tokens, profile.max_memory_items, profile.max_session_items,
                          profile.max_item_tokens, profile.min_score, profile.include_explanations,
                          profile.include_session_summary, profile.omit_repeated_items)
