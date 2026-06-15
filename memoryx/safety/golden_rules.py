"""Golden Rules System — user corrections are absolute and inviolable.

When a user corrects the agent ("No, I don't like Python", "Always use tabs"),
that correction becomes a Golden Rule:
- Highest retrieval priority (overrides all other memories)
- Cannot be overridden by lower-confidence memories
- Actively suppresses contradictory memories
- Enforced at the retrieval layer, not just stored

Based on:
- Reinforcement Learning from Human Feedback (RLHF): reward shaping
- Constitutional AI: explicit rule hierarchy
- Cognitive dissonance resolution: high-certainty beliefs dominate
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from memoryx.temporal.time_provider import TimeProvider, get_time_provider

logger = logging.getLogger(__name__)

# Golden rules have infinite priority — they always win
_GOLDEN_RULE_PRIORITY: float = float("inf")

# Confidence threshold for a user correction to become golden
# User corrections are treated as ground truth (1.0 confidence)
_USER_CORRECTION_CONFIDENCE: float = 1.0

# Patterns that indicate user correction/override
_CORRECTION_PATTERNS: list[str] = [
    r"\bno[,.]?\s+i\s+(?:don't|do not|never|hate|dislike)",
    r"\bactually[,.]?\s+i\s+",
    r"\bwrong[,.]?\s+i\s+",
    r"\bincorrect[,.]?\s+i\s+",
    r"\bthat's not right[,.]?\s+i\s+",
    r"\b不是[，。]?\s*我",
    r"\b错了[，。]?\s*我",
    r"\b不对[，。]?\s*我",
    r"\balways\s+(?:use|do|prefer|choose)",
    r"\bnever\s+(?:use|do|prefer|choose)",
    r"\b必须\s+",
    r"\b一定\s+",
    r"\b绝(?:对|不)\s+",
]

_CORRECTION_RE: list[re.Pattern[str]] = [re.compile(p, re.IGNORECASE) for p in _CORRECTION_PATTERNS]


@dataclass
class GoldenRule:
    """A user-corrected memory with absolute authority."""

    rule_id: str
    memory_id: str  # Links to the memory in the main DB
    content: str  # The corrected fact/rule
    original_content: str | None = None  # What the agent got wrong
    correction_source: str = "user_explicit"  # user_explicit | user_implicit
    confidence: float = _USER_CORRECTION_CONFIDENCE
    created_at: datetime = field(default_factory=lambda: datetime.now())
    # What this rule contradicts and suppresses
    suppresses_patterns: list[str] = field(default_factory=list)
    # Scope: global | session | user
    scope: str = "global"
    session_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class GoldenRuleEngine:
    """Manages user corrections as inviolable golden rules.

    Responsibilities:
    1. Detect user corrections from natural language
    2. Promote corrected memories to golden status
    3. Enforce golden rules at retrieval time (boost + suppress contradictions)
    4. Prevent "memory regression" — old wrong memories cannot override golden rules
    """

    def __init__(
        self,
        *,
        repository=None,
        time_provider: TimeProvider | None = None,
        max_rules: int = 10000,
    ) -> None:
        self.repository = repository
        self.time_provider = time_provider or get_time_provider()
        self._rules: dict[str, GoldenRule] = {}
        self._lock = asyncio.Lock()
        self._max_rules = max_rules

    # ── Detection ─────────────────────────────────────────────────

    def detect_correction(self, content: str) -> bool:
        """Detect if user message contains a correction."""
        for pattern in _CORRECTION_RE:
            if pattern.search(content):
                return True
        return False

    def extract_corrected_fact(self, content: str) -> str | None:
        """Extract the corrected fact from a correction message.

        Simple heuristic: take the sentence after the correction marker.
        Production would use LLM extraction.
        """
        # Try to find "X is actually Y" patterns
        patterns = [
            r"(?:no|actually|wrong|incorrect)[,;.!?\s]+(.+?)(?:[.!?]|$)",
            r"(?:不是|错了|不对)[，。;！?\s]+(.+?)(?:[。！?]|$)",
            r"(?:always|never)\s+(.+?)(?:[.!?]|$)",
        ]
        for p in patterns:
            m = re.search(p, content, re.IGNORECASE)
            if m:
                return m.group(1).strip()
        return None

    # ── Rule Management ───────────────────────────────────────────

    async def create_golden_rule(
        self,
        *,
        memory_id: str,
        corrected_content: str,
        original_content: str | None = None,
        suppresses_patterns: list[str] | None = None,
        scope: str = "global",
        session_id: str | None = None,
    ) -> GoldenRule:
        """Create a new golden rule from a user correction."""
        async with self._lock:
            rule_id = f"golden_{memory_id}_{int(self.time_provider.time())}"
            rule = GoldenRule(
                rule_id=rule_id,
                memory_id=memory_id,
                content=corrected_content,
                original_content=original_content,
                correction_source="user_explicit",
                confidence=_USER_CORRECTION_CONFIDENCE,
                created_at=self.time_provider.now(),
                suppresses_patterns=list(suppresses_patterns) if suppresses_patterns else [],
                scope=scope,
                session_id=session_id,
            )
            self._rules[rule_id] = rule
            await self._persist_rule(rule)
            await self._enforce_max_rules()

            # Also mark the underlying memory as golden
            if self.repository is not None:
                try:
                    await self.repository.db.execute(
                        "UPDATE memories SET is_golden = 1, golden_priority = ? WHERE id = ?;",
                        (_GOLDEN_RULE_PRIORITY, memory_id),
                    )
                except Exception:
                    logger.exception("Failed to mark memory %s as golden", memory_id)

            logger.info("Created golden rule %s: %s", rule_id, corrected_content[:80])
            return rule

    async def get_rules_for_query(self, query: str, session_id: str | None = None) -> list[GoldenRule]:
        """Get all golden rules relevant to a query."""
        async with self._lock:
            results: list[GoldenRule] = []
            query_lower = query.lower()
            query_words = set(query_lower.split())

            for rule in self._rules.values():
                # Scope check
                if rule.scope == "session" and rule.session_id != session_id:
                    continue

                # Relevance check: keyword overlap
                rule_words = set(rule.content.lower().split())
                overlap = len(query_words & rule_words)
                if overlap > 0 or any(pattern in query_lower for pattern in rule.suppresses_patterns):
                    results.append(rule)

            return results

    async def apply_golden_rules(
        self,
        memories: list[dict[str, Any]],
        query: str,
        session_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Apply golden rules to a memory retrieval result set.

        1. Boost golden memories to the top
        2. Suppress memories that contradict golden rules
        3. Return the filtered and reordered list
        """
        rules = await self.get_rules_for_query(query, session_id)
        if not rules:
            return memories

        golden_memory_ids = {r.memory_id for r in rules}
        suppressed_ids: set[str] = set()

        for rule in rules:
            for pattern in rule.suppresses_patterns:
                for mem in memories:
                    mem_id = mem.get("id", "")
                    if mem_id in golden_memory_ids:
                        continue  # Never suppress another golden rule
                    content = mem.get("content", "")
                    if pattern.lower() in content.lower():
                        suppressed_ids.add(mem_id)
                        mem["_suppressed_by_golden_rule"] = rule.rule_id
                        mem["_suppression_reason"] = f"Contradicts golden rule: {rule.content[:60]}"

        # Reorder: golden rules first, then non-suppressed, then suppressed
        def sort_key(mem: dict[str, Any]) -> tuple[int, float]:
            mem_id = mem.get("id", "")
            if mem_id in golden_memory_ids:
                return (0, -mem.get("score", 0))
            if mem_id in suppressed_ids:
                return (2, -mem.get("score", 0))
            return (1, -mem.get("score", 0))

        sorted_memories = sorted(memories, key=sort_key)
        return sorted_memories

    async def is_contradicted_by_golden_rule(self, content: str, session_id: str | None = None) -> GoldenRule | None:
        """Check if a proposed memory content contradicts any golden rule."""
        async with self._lock:
            content_lower = content.lower()
            for rule in self._rules.values():
                if rule.scope == "session" and rule.session_id != session_id:
                    continue
                for pattern in rule.suppresses_patterns:
                    if pattern.lower() in content_lower:
                        return rule
            return None

    # ── Persistence ───────────────────────────────────────────────

    async def _persist_rule(self, rule: GoldenRule) -> None:
        if self.repository is None:
            return
        try:
            await self.repository.db.execute(
                "INSERT INTO golden_rules(rule_id, memory_id, content, original_content, "
                "correction_source, confidence, created_at, suppresses_patterns, scope, session_id, metadata) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(rule_id) DO UPDATE SET "
                "content=excluded.content, suppresses_patterns=excluded.suppresses_patterns, "
                "metadata=excluded.metadata;",
                (
                    rule.rule_id,
                    rule.memory_id,
                    rule.content,
                    rule.original_content,
                    rule.correction_source,
                    rule.confidence,
                    rule.created_at.isoformat(),
                    json.dumps(rule.suppresses_patterns),
                    rule.scope,
                    rule.session_id,
                    json.dumps(rule.metadata),
                ),
            )
        except Exception:
            logger.exception("Failed to persist golden rule %s", rule.rule_id)

    async def load_rules_from_db(self) -> int:
        """Load all golden rules from DB on startup."""
        if self.repository is None:
            return 0
        try:
            rows = await self.repository.db.fetchall(
                "SELECT rule_id, memory_id, content, original_content, correction_source, "
                "confidence, created_at, suppresses_patterns, scope, session_id, metadata "
                "FROM golden_rules;"
            )
            count = 0
            for row in rows:
                rule = GoldenRule(
                    rule_id=row[0],
                    memory_id=row[1],
                    content=row[2],
                    original_content=row[3],
                    correction_source=row[4],
                    confidence=row[5],
                    created_at=datetime.fromisoformat(row[6]),
                    suppresses_patterns=json.loads(row[7]) if row[7] else [],
                    scope=row[8],
                    session_id=row[9],
                    metadata=json.loads(row[10]) if row[10] else {},
                )
                self._rules[rule.rule_id] = rule
                count += 1
            return count
        except Exception:
            logger.exception("Failed to load golden rules from DB")
            return 0

    # ── Rule deletion and pruning ─────────────────────────────────

    async def delete_rule(self, rule_id: str) -> bool:
        """Delete a single golden rule by ID. Returns True if found and deleted."""
        async with self._lock:
            if rule_id not in self._rules:
                return False
            del self._rules[rule_id]
            if self.repository is not None:
                try:
                    await self.repository.db.execute(
                        "DELETE FROM golden_rules WHERE rule_id = ?;",
                        (rule_id,),
                    )
                except Exception:
                    logger.exception("Failed to delete golden rule %s from DB", rule_id)
            logger.info("Deleted golden rule %s", rule_id)
            return True

    async def prune_session_rules(self, session_id: str) -> int:
        """Remove all session-scoped rules for the given session. Returns count pruned."""
        async with self._lock:
            to_delete = [
                rid for rid, rule in self._rules.items()
                if rule.scope == "session" and rule.session_id == session_id
            ]
            for rid in to_delete:
                del self._rules[rid]
            if self.repository is not None and to_delete:
                try:
                    await self.repository.db.execute(
                        "DELETE FROM golden_rules WHERE scope = 'session' AND session_id = ?;",
                        (session_id,),
                    )
                except Exception:
                    logger.exception("Failed to prune session rules for %s from DB", session_id)
            if to_delete:
                logger.info("Pruned %d session rules for session %s", len(to_delete), session_id)
            return len(to_delete)

    async def _enforce_max_rules(self) -> None:
        """Enforce max_rules cap by removing oldest session-scoped rules first."""
        while len(self._rules) > self._max_rules:
            # Find oldest session-scoped rule
            oldest_session_rule: GoldenRule | None = None
            for rule in self._rules.values():
                if rule.scope == "session":
                    if oldest_session_rule is None or rule.created_at < oldest_session_rule.created_at:
                        oldest_session_rule = rule
            if oldest_session_rule is not None:
                await self.delete_rule(oldest_session_rule.rule_id)
                continue
            # No session rules left; remove oldest global rule
            oldest_rule = min(self._rules.values(), key=lambda r: r.created_at)
            await self.delete_rule(oldest_rule.rule_id)
