from __future__ import annotations
from dataclasses import dataclass, asdict, field
from typing import Any
from .policy import ContextBudgetPolicy
from .tokens import TokenEstimator

@dataclass(frozen=True)
class ContextItem:
    item_id: str; section: str; content: str; score: float = 0.0; item_type: str = "memory"; metadata: dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True)
class ContextPack:
    schema: str; request_id: str; session_id: str | None; query: str; max_tokens: int; used_tokens: int
    included_items: int; dropped_items: int; sections: dict[str, list[dict[str, Any]]]; warnings: list[str]; text: str
    mode: str = "standard"; pack_id: str | None = None; diff: dict[str, Any] = field(default_factory=dict)
    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["cache_layout"] = {
            "omitted_repeated_item_ids": getattr(self, '_omitted_repeated_item_ids', []),
            "previous_repeated_count": getattr(self, '_previous_repeated_count', 0),
        }
        return d

class ContextPacker:
    def __init__(self, policy: ContextBudgetPolicy | None = None, estimator: TokenEstimator | None = None):
        self.policy = policy or ContextBudgetPolicy.from_env(); self.estimator = estimator or TokenEstimator()

    def pack(self, *, request_id: str, session_id: str | None, query: str, items: list[ContextItem],
             mode: str = "standard", pack_id: str | None = None,
             previous_item_ids: set[str] | None = None, omit_repeated_items: bool = False) -> ContextPack:
        max_tokens = self.policy.memory_budget_tokens(); remaining = max_tokens; warnings: list[str] = []
        sections = {"task_focus": [], "relevant_memories": [], "session_context": [], "session_summary": [], "metadata": []}
        task_focus = self.estimator.truncate_to_tokens(query, self.policy.section_budget("task_focus"))
        task_tokens = self.estimator.estimate_text(task_focus).estimated_tokens
        sections["task_focus"].append({"content": task_focus, "estimated_tokens": task_tokens}); remaining -= task_tokens
        dropped = 0; included = 0; repeated = 0; omitted_repeated = []; section_used: dict[str, int] = {}
        previous_item_ids = previous_item_ids or set()

        for item in sorted(items, key=lambda x: (-x.score, x.item_id)):
            if omit_repeated_items and item.item_id in previous_item_ids and item.section == "relevant_memories":
                repeated += 1; omitted_repeated.append(item.item_id); continue
            if item.score < self.policy.min_score and item.section == "relevant_memories": dropped += 1; continue
            if item.section == "relevant_memories" and sum(1 for x in sections["relevant_memories"]) >= self.policy.max_memory_items: dropped += 1; continue
            if item.section in {"session_context", "session_summary"} and sum(1 for x in sections.get(item.section, [])) >= self.policy.max_session_items: dropped += 1; continue

            s_cap = self.policy.section_budget("session_context" if item.section == "session_summary" else item.section)
            used = section_used.get(item.section, 0)
            item_budget = min(self.policy.max_item_tokens, max(0, s_cap - used), max(0, remaining))
            if item_budget <= 8: dropped += 1; continue
            content = self.estimator.truncate_to_tokens(item.content, item_budget)
            tc = self.estimator.estimate_text(content).estimated_tokens
            if tc > remaining: dropped += 1; continue
            entry = {"id": item.item_id, "type": item.item_type, "content": content, "score": round(item.score, 4), "estimated_tokens": tc}
            if item.metadata:
                safe = {k: v for k, v in item.metadata.items() if k in {"claim_type", "status", "confidence", "source", "created_at", "updated_at", "summary_updated_at", "turn_count"}}
                if safe: entry["metadata"] = safe
            sections.setdefault(item.section, []).append(entry); section_used[item.section] = used + tc; remaining -= tc; included += 1

        used = max_tokens - remaining
        if dropped: warnings.append(f"dropped {dropped} items due to budget/scope/score limits")
        if repeated: warnings.append(f"omitted {repeated} repeated items from previous pack")

        lines = ["# MemoryX Context Pack", "", "## Task Focus", query.strip()]
        if sections.get("session_summary"):
            lines.extend(["", "## Session Summary"])
            for item in sections["session_summary"]: lines.append(f"- {item['content']}")
        lines.extend(["", "## Relevant Memories"])
        if sections.get("relevant_memories"):
            for item in sections["relevant_memories"]: lines.append(f"- ({item['score']:.4f}) {item['content']}")
        else: lines.append("- No relevant memories selected within budget.")
        if sections.get("session_context"):
            lines.extend(["", "## Session Context"])
            for item in sections["session_context"]: lines.append(f"- {item['content']}")
        if warnings:
            lines.extend(["", "## Warnings"])
            for w in warnings: lines.append(f"- {w}")
        text = "\n".join(lines)

        return ContextPack("memoryx.context_pack.v1", request_id, session_id, query, max_tokens, used,
                           included, dropped + repeated, sections, warnings, text,
                           mode=mode, pack_id=pack_id, diff={"previous_repeated_count": repeated, "omitted_repeated_item_ids": omitted_repeated})
