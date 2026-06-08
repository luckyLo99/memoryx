from pathlib import Path
import textwrap

ROOT = Path.cwd()
written = []

def write(path, content):
    p = ROOT / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(textwrap.dedent(content).lstrip(), encoding="utf-8")
    written.append(path)
    print(f"[WRITE] {path}")

# ===== profiles.py =====
write("memoryx/context_budget/profiles.py", '''
from __future__ import annotations
from dataclasses import dataclass

ContextMode = "tiny" | "brief" | "standard" | "deep" | "debug"

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
}

def get_context_profile(mode: str | None = None) -> ContextProfile:
    key = (mode or "standard").lower()
    return CONTEXT_PROFILES.get(key, CONTEXT_PROFILES["standard"])

def clamp_profile_to_model_window(profile: ContextProfile, model_window_tokens: int) -> ContextProfile:
    cap = max(1024, int(model_window_tokens * 0.08))
    max_tokens = min(profile.max_context_tokens, cap)
    return ContextProfile(profile.mode, max_tokens, profile.max_memory_items, profile.max_session_items,
                          profile.max_item_tokens, profile.min_score, profile.include_explanations,
                          profile.include_session_summary, profile.omit_repeated_items)
''')

# ===== planner.py =====
write("memoryx/context_budget/planner.py", '''
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
        elif matches_any(q, BRIEF_PATTERNS) or len(q) < 80: selected = "brief"; reason = "matched brief intent"
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
''')

# ===== session_summary.py =====
write("memoryx/context_budget/session_summary.py", '''
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import sqlite3
from typing import Any
from memoryx.storage import connect_hardened
from .tokens import TokenEstimator

def utc_iso(): return datetime.now(timezone.utc).isoformat()
def hash_text(text): return hashlib.sha256((text or "").encode("utf-8")).hexdigest()

@dataclass(frozen=True)
class SessionSummary:
    session_id: str; summary: str; source_hash: str; updated_at: str; turn_count: int

class SessionSummaryStore:
    def __init__(self, db_path: str):
        self.db_path = db_path
        with sqlite3.connect(db_path) as con:
            con.execute("CREATE TABLE IF NOT EXISTS memoryx_session_summaries (session_id TEXT PRIMARY KEY, summary TEXT NOT NULL, source_hash TEXT NOT NULL, turn_count INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
            con.commit()

    def get(self, session_id: str | None) -> SessionSummary | None:
        if not session_id: return None
        with sqlite3.connect(self.db_path) as con:
            con.row_factory = sqlite3.Row
            row = con.execute("SELECT session_id, summary, source_hash, updated_at, turn_count FROM memoryx_session_summaries WHERE session_id = ?", (session_id,)).fetchone()
        return SessionSummary(row["session_id"], row["summary"], row["source_hash"], row["updated_at"], int(row["turn_count"])) if row else None

    def upsert_from_history(self, session_id: str, session_history: list[str], max_summary_tokens: int = 512) -> SessionSummary:
        estimator = TokenEstimator()
        clean = [x.strip() for x in session_history if x and x.strip()]
        source = "\n".join(clean)
        source_hash = hash_text(source)
        existing = self.get(session_id)
        if existing and existing.source_hash == source_hash: return existing

        important = [t for t in clean if any(k in t.lower() for k in ["todo", "decision", "决定", "任务", "phase", "error", "bug", "fix", "patch"])]
        first = clean[:2]; last = clean[-4:]
        selected = []
        for item in first + important + last:
            if item not in selected: selected.append(item)
        summary = "Session summary:\n" + "\n".join(f"- {item}" for item in selected)
        summary = estimator.truncate_to_tokens(summary, max_summary_tokens)
        now = utc_iso()
        with sqlite3.connect(self.db_path) as con:
            con.execute("INSERT INTO memoryx_session_summaries(session_id, summary, source_hash, turn_count, updated_at) VALUES (?, ?, ?, ?, ?) ON CONFLICT(session_id) DO UPDATE SET summary=excluded.summary, source_hash=excluded.source_hash, turn_count=excluded.turn_count, updated_at=excluded.updated_at", (session_id, summary, source_hash, len(clean), now))
            con.commit()
        return SessionSummary(session_id, summary, source_hash, now, len(clean))
''')

# ===== diff.py =====
write("memoryx/context_budget/diff.py", '''
from __future__ import annotations
from dataclasses import dataclass
import json, sqlite3
from typing import Any

@dataclass(frozen=True)
class ContextPackDiff:
    previous_pack_id: str | None; current_pack_id: str; repeated_item_ids: list[str]; new_item_ids: list[str]; omitted_repeated_item_ids: list[str]

class ContextPackHistory:
    def __init__(self, db_path: str):
        self.db_path = db_path
        with sqlite3.connect(db_path) as con:
            con.execute("CREATE TABLE IF NOT EXISTS memoryx_context_packs (pack_id TEXT PRIMARY KEY, session_id TEXT, request_id TEXT NOT NULL, query TEXT NOT NULL, item_ids_json TEXT NOT NULL, used_tokens INTEGER NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
            con.execute("CREATE INDEX IF NOT EXISTS idx_memoryx_context_packs_session_created ON memoryx_context_packs(session_id, created_at)")
            con.commit()

    def get_item_ids(self, pack_id: str | None) -> list[str]:
        if not pack_id: return []
        with sqlite3.connect(self.db_path) as con:
            con.row_factory = sqlite3.Row
            row = con.execute("SELECT item_ids_json FROM memoryx_context_packs WHERE pack_id = ?", (pack_id,)).fetchone()
        return list(json.loads(row["item_ids_json"])) if row else []

    def record_pack(self, *, pack_id: str, session_id: str | None, request_id: str, query: str, item_ids: list[str], used_tokens: int):
        with sqlite3.connect(self.db_path) as con:
            con.execute("INSERT OR REPLACE INTO memoryx_context_packs(pack_id, session_id, request_id, query, item_ids_json, used_tokens) VALUES (?, ?, ?, ?, ?, ?)", (pack_id, session_id, request_id, query, json.dumps(item_ids), int(used_tokens)))
            con.commit()

    def diff(self, previous_pack_id: str | None, current_item_ids: list[str], current_pack_id: str) -> ContextPackDiff:
        prev = set(self.get_item_ids(previous_pack_id)); cur = set(current_item_ids)
        return ContextPackDiff(previous_pack_id, current_pack_id, sorted(prev & cur), sorted(cur - prev), [])
''')

# ===== __init__.py (updated) =====
write("memoryx/context_budget/__init__.py", '''
from __future__ import annotations
from .tokens import TokenEstimate, TokenEstimator
from .policy import ContextBudgetPolicy
from .profiles import ContextProfile, get_context_profile, clamp_profile_to_model_window
from .planner import AdaptiveContextPlanner, ContextPlan
from .packer import ContextItem, ContextPack, ContextPacker
from .assembler import BudgetedContextAssembler
from .run_guard import RequestLease, ActiveRequestStore
from .session_summary import SessionSummary, SessionSummaryStore
from .diff import ContextPackHistory, ContextPackDiff
__all__ = ["TokenEstimate", "TokenEstimator", "ContextBudgetPolicy", "ContextProfile",
           "get_context_profile", "clamp_profile_to_model_window", "AdaptiveContextPlanner",
           "ContextPlan", "ContextItem", "ContextPack", "ContextPacker", "BudgetedContextAssembler",
           "RequestLease", "ActiveRequestStore", "SessionSummary", "SessionSummaryStore",
           "ContextPackHistory", "ContextPackDiff"]
''')

# ===== packer.py (updated) =====
write("memoryx/context_budget/packer.py", '''
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
    def to_dict(self) -> dict[str, Any]: return asdict(self)

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
''')

# ===== assembler.py (updated) =====
write("memoryx/context_budget/assembler.py", '''
from __future__ import annotations
import uuid
from typing import Any
from memoryx.core.hybrid_retriever import HybridRetriever
from memoryx.core.types import SearchOptions
from memoryx.core.vector import NullVectorProvider
from .diff import ContextPackHistory
from .packer import ContextItem, ContextPacker
from .planner import AdaptiveContextPlanner
from .policy import ContextBudgetPolicy
from .run_guard import ActiveRequestStore
from .session_summary import SessionSummaryStore

class BudgetedContextAssembler:
    def __init__(self, db_path: str, policy: ContextBudgetPolicy | None = None):
        self.db_path = db_path; self.policy = policy
        self.guard = ActiveRequestStore(db_path); self.summary_store = SessionSummaryStore(db_path); self.history = ContextPackHistory(db_path)

    def assemble(self, *, query: str, session_id=None, agent_id=None, user_id=None, request_id=None,
                 session_history=None, limit=None, begin_request=True, mode=None, previous_pack_id=None) -> dict[str, Any]:
        rid = request_id or uuid.uuid4().hex; pack_id = uuid.uuid4().hex
        planner = AdaptiveContextPlanner(); plan = planner.plan(query, requested_mode=mode)
        policy = self.policy or plan.policy; packer = ContextPacker(policy)
        if begin_request:
            lease = self.guard.begin_request(session_id=session_id, task_text=query, request_id=rid); rid = lease.request_id
        stale = self.guard.reject_if_stale(rid, session_id)
        if stale: return stale

        retriever = HybridRetriever(self.db_path, NullVectorProvider())
        rl = min(max(limit or policy.max_memory_items * 2, 1), policy.max_memory_items * 4)
        hits = retriever.search(query, limit=rl, options=SearchOptions(limit=rl, mode="auto", min_score=0.0, reject_low_confidence=False, include_inactive=False, explain=policy.include_explanations))
        items: list[ContextItem] = []

        if session_id and session_history and plan.profile.include_session_summary:
            summary = self.summary_store.upsert_from_history(session_id, session_history, max_summary_tokens=min(512, policy.max_item_tokens))
            if summary.summary:
                items.append(ContextItem(f"session_summary:{session_id}", "session_summary", summary.summary, 0.70, "session_summary", {"summary_updated_at": summary.updated_at, "turn_count": summary.turn_count}))

        for hit in hits:
            meta = {"claim_type": hit.claim_type, "status": hit.status}
            if policy.include_explanations: meta["explanation"] = hit.explanation
            items.append(ContextItem(hit.claim_id, "relevant_memories", hit.content, float(hit.final_score), hit.claim_type, meta))

        prev_ids = set(self.history.get_item_ids(previous_pack_id))
        pack = packer.pack(request_id=rid, session_id=session_id, query=query, items=items, mode=plan.mode,
                           pack_id=pack_id, previous_item_ids=prev_ids, omit_repeated_items=plan.profile.omit_repeated_items and bool(previous_pack_id))
        included_ids = [item["id"] for sec in pack.sections.values() for item in sec if item.get("id")]
        self.history.record_pack(pack_id=pack_id, session_id=session_id, request_id=rid, query=query, item_ids=included_ids, used_tokens=pack.used_tokens)

        stale2 = self.guard.reject_if_stale(rid, session_id)
        if stale2: return stale2
        self.guard.complete_request(rid, "completed")
        return {"ok": True, "request_id": rid, "session_id": session_id, "agent_id": agent_id, "user_id": user_id,
                "context_pack": pack.to_dict(),
                "instruction_context": [item for item in pack.sections.get("relevant_memories", []) if item.get("type") in {"instruction", "preference", "task_state"}],
                "evidence_context": [item for item in pack.sections.get("relevant_memories", []) if item.get("type") not in {"instruction", "preference", "task_state"}],
                "session_context": [],
                "provenance": {"assembler": "BudgetedContextAssembler", "planner": "AdaptiveContextPlanner",
                    "mode": plan.mode, "plan_reason": plan.reason, "schema": pack.schema, "pack_id": pack_id,
                    "previous_pack_id": previous_pack_id, "max_tokens": pack.max_tokens, "used_tokens": pack.used_tokens,
                    "included_items": pack.included_items, "dropped_items": pack.dropped_items,
                    "budget_policy": {"max_context_tokens": policy.max_context_tokens, "max_memory_items": policy.max_memory_items,
                        "max_item_tokens": policy.max_item_tokens, "min_score": policy.min_score,
                        "session_history_injected_raw": False, "session_summary_enabled": plan.profile.include_session_summary}}}
''')

print(f"\n[DONE] {len(written)} files written")
for w in written: print(f"  {w}")
