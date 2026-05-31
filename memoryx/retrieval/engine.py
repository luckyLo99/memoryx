from __future__ import annotations

import hashlib
import json
import logging
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from .models import RetrievalIntent, RetrievalResult, RetrievalTrace

logger = logging.getLogger(__name__)


def _is_visible_memory_for_retrieval(
    record: dict[str, Any],
    include_candidates: bool = False,
) -> bool:
    """Determine if a memory record should be visible in retrieval results.

    Rules:
    - metadata_json has no candidate_state: legacy committed, visible
    - candidate_state in [committed, verified]: visible
    - candidate_state == "candidate": only if include_candidates=True
    - candidate_state in [rejected, superseded, stale]: never visible
    - metadata_json invalid: conservatively visible (avoid killing old data)
    """
    raw_meta = record.get("metadata_json", "{}")
    try:
        meta = json.loads(raw_meta) if raw_meta else {}
    except (json.JSONDecodeError, ValueError):
        return True  # conservative: don't kill old data on parse failure

    cs = meta.get("candidate_state")
    if cs is None:
        return True  # legacy committed, always visible

    if cs in ("committed", "verified"):
        return True
    if cs == "candidate":
        return include_candidates
    # rejected, superseded, stale — never visible
    return False


def _is_session_scoped_memory(record: dict[str, Any]) -> bool:
    """Check if a memory is session-scoped (scope=session or memory_layer=session).

    Returns True if the memory belongs to a specific session.
    Does NOT check if it matches the current session_id.
    """
    raw_meta = record.get("metadata_json", "{}")
    try:
        meta = json.loads(raw_meta) if raw_meta else {}
    except (json.JSONDecodeError, ValueError):
        meta = {}
    return record.get("scope") == "session" or meta.get("memory_layer") == "session"


def _session_matches(record: dict[str, Any], session_id: str | None) -> bool:
    """Check if a memory's session_id matches the given session_id.

    Returns False if either side is None.
    """
    if not session_id:
        return False
    mem_session = record.get("session_id")
    return bool(mem_session) and mem_session == session_id


def _is_lesson_memory(record: dict[str, Any]) -> bool:
    """Check if a memory record is a LESSON.

    Primary criterion: memory_type == "LESSON".
    Fallback: metadata.memory_class == "lesson".
    """
    if record.get("memory_type") == "LESSON":
        return True
    raw_meta = record.get("metadata_json", "{}")
    try:
        meta = json.loads(raw_meta) if raw_meta else {}
    except (json.JSONDecodeError, ValueError):
        meta = {}
    return meta.get("memory_class") == "lesson"


def _layer_score_boost(record: dict[str, Any]) -> float:
    """Return a deterministic layer-based score boost (24.4-B).

    Only applies to memories that have already passed eligibility.
    policy/guard get highest boost, project moderate, session slight.
    long_term and legacy get no boost.
    """
    raw_meta = record.get("metadata_json", "{}")
    try:
        meta = json.loads(raw_meta) if raw_meta else {}
    except (json.JSONDecodeError, ValueError):
        meta = {}
    layer = meta.get("memory_layer", "")
    if layer in ("policy", "guard"):
        return 0.30
    if layer == "project":
        return 0.15
    if layer == "session":
        return 0.10
    return 0.0


def _retrieval_dedup_key(record: dict[str, Any], memory_type: str = "") -> str:
    """Return a deduplication key for a memory record.

    Based on content + memory_type + layer. Not a cryptographic hash,
    just a deterministic grouping key.
    """
    content = (record.get("content") or "").strip().lower()
    mt = memory_type or record.get("memory_type", "")
    raw_meta = record.get("metadata_json", "{}")
    try:
        meta = json.loads(raw_meta) if raw_meta else {}
    except (json.JSONDecodeError, ValueError):
        meta = {}
    layer = meta.get("memory_layer", "")
    return hashlib.sha256(f"{mt}|{layer}|{content}".encode("utf-8")).hexdigest()


MIN_FINAL_SCORE = 0.05


class HybridRetrievalEngine:
    def __init__(self, *, repository, vector_store) -> None:
        self.repository = repository
        self.vector_store = vector_store

    async def retrieve(
        self,
        *,
        query: str,
        query_vector: list[float],
        limit: int = 10,
        intent: RetrievalIntent | None = None,
        scope_filter: str | None = None,
        session_id: str | None = None,
        include_global: bool = True,
        include_lessons: bool = True,
        include_candidates: bool = False,
        session_only: bool = False,
        explain_scores: bool = False,
        tag_filter: list[str] | None = None,
        tag_mode: str = "any",
        fusion_method: str = "weighted",
    ) -> list[RetrievalResult]:
        # Build visibility filter for session isolation
        visibility_sql, visibility_params = self._build_visibility_filter(
            session_id=session_id,
            scope_filter=scope_filter,
            include_global=include_global,
            session_only=session_only,
        )

        vector_hits: list[dict] = []
        vector_available = False
        if self.vector_store is not None:
            try:
                vector_hits = await self.vector_store.search(query_vector, limit=max(limit * 3, 10))
                vector_available = True
            except Exception:
                vector_hits = []  # degraded: vector unavailable
        vector_scores = {item["memory_id"]: float(item["score"]) for item in vector_hits}

        # 24.4-B: fetch_limit optimization — base 2x, fallback 3x if needed
        base_fetch = max(limit * 2, 30)
        fallback_fetch = max(limit * 3, 30)
        if explain_scores:
            keyword_hits, fts_trace = await self.repository.search_full_text_with_trace(query, limit=base_fetch)
        else:
            keyword_hits = await self.repository.search_full_text(query, limit=base_fetch)
            fts_trace = {"query_plan_used": None, "fallback_steps": [], "raw_hit_count": len(keyword_hits)}
        keyword_map = {item["memory_id"]: item for item in keyword_hits}

        candidate_ids = list(dict.fromkeys([*vector_scores.keys(), *keyword_map.keys()]))
        raw_hit_count = len(candidate_ids)
        memories: list[dict[str, Any]] = []
        seen_dedup: dict[str, float] = {}  # dedup_key -> best_score (24.4-B)
        hidden_candidates = 0
        hidden_session = 0
        hidden_lessons = 0
        hidden_state = 0
        dedup_dropped = 0
        for memory_id in candidate_ids:
            memory = await self.repository.get_memory(memory_id)
            if memory is None:
                continue

            # Session isolation: filter by session_id and scope
            mem_scope = str(memory.get("scope", "global"))
            mem_session = memory.get("session_id")

            # Scope filter
            if scope_filter is not None and mem_scope != scope_filter:
                continue

            # Session isolation
            if session_id is not None:
                if mem_scope == "global":
                    pass  # always visible when include_global=True
                elif mem_session == session_id:
                    pass  # same session
                elif include_global and mem_scope == "global":
                    pass
                else:
                    hidden_session += 1
                    continue  # different session, exclude
            elif not include_global:
                if mem_scope == "global":
                    hidden_state += 1
                    continue

            # Session scope hardening (24.3C)
            if _is_session_scoped_memory(memory):
                if not _session_matches(memory, session_id):
                    hidden_session += 1
                    continue  # foreign session-scoped memory never visible
            if session_only:
                if not _is_session_scoped_memory(memory):
                    hidden_session += 1
                    continue  # session_only excludes global/user/project
                if not _session_matches(memory, session_id):
                    hidden_session += 1
                    continue  # must also match session_id

            if tag_filter and not self._match_tags(memory.get("tags_json", "[]"), tag_filter, tag_mode):
                continue

            # Candidate visibility filter: exclude candidate/rejected/superseded/stale
            if not _is_visible_memory_for_retrieval(memory, include_candidates=include_candidates):
                hidden_candidates += 1
                continue

            # Lesson inclusion filter: exclude LESSON when include_lessons=False
            if not include_lessons and _is_lesson_memory(memory):
                hidden_lessons += 1
                continue

            # 24.4-B: retrieval-level dedup
            dk = _retrieval_dedup_key(memory)
            est_score = vector_scores.get(memory_id, 0.0)
            if dk in seen_dedup:
                if est_score <= seen_dedup[dk]:
                    dedup_dropped += 1
                    continue  # lower or equal score, skip
            seen_dedup[dk] = est_score

            memories.append(memory)

        weights = self._intent_weights(intent)
        results: list[RetrievalResult] = []
        now = datetime.now(timezone.utc)
        query_tokens = self._tokens(query)
        layer_boost_applied = 0
        fallback_used = False

        for memory in memories:
            memory_id = str(memory.get("id") or memory.get("memory_id"))
            content = str(memory["content"])
            semantic_score = vector_scores.get(memory_id, 0.0)
            keyword_score = self._keyword_overlap(query_tokens, self._tokens(content))
            importance_score = float(memory.get("importance_score", 0.0))
            entity_score = self._entity_overlap(query_tokens, memory.get("entities_json", "[]"))
            episodic_score = 0.15 if str(memory.get("memory_type", "")) == "EPISODIC" else 0.0
            temporal_score = self._temporal_score(str(memory.get("valid_from") or memory.get("updated_at") or ""), now)

            final_score = (
                semantic_score * weights["semantic"]
                + keyword_score * weights["keyword"]
                + temporal_score * weights["temporal"]
                + entity_score * weights["entity"]
                + importance_score * weights["importance"]
                + episodic_score * weights["episodic"]
            )

            # 24.4-B: layer-aware score boost
            layer_boost = _layer_score_boost(memory)
            final_score += layer_boost
            if layer_boost:
                layer_boost_applied += 1

            explanation = self._build_explanation(
                semantic_score=semantic_score,
                keyword_score=keyword_score,
                temporal_score=temporal_score,
                entity_score=entity_score,
                importance_score=importance_score,
                episodic_score=episodic_score,
                intent=intent,
            )
            if layer_boost:
                explanation += f", layer_boost={layer_boost:.2f}"

            results.append(
                RetrievalResult(
                    memory_id=memory_id,
                    content=content,
                    memory_type=str(memory.get("memory_type", "")),
                    scope=str(memory.get("scope", "global")),
                    semantic_score=semantic_score,
                    keyword_score=keyword_score,
                    temporal_score=temporal_score,
                    entity_score=entity_score,
                    importance_score=importance_score,
                    episodic_score=episodic_score,
                    final_score=final_score,
                    explanation=explanation,
                )
            )

        results.sort(key=lambda item: item.final_score, reverse=True)

        # 24.4-B: fallback fetch if results < limit and base_fetch was fully utilized
        if len(results) < limit and len(keyword_hits) >= base_fetch:
            fallback_used = True
            more_hits = await self.repository.search_full_text(query, limit=fallback_fetch)
            new_ids = {m["memory_id"] for m in more_hits} - {r.memory_id for r in results}
            for memory_id in new_ids:
                memory = await self.repository.get_memory(memory_id)
                if memory is None:
                    continue
                if _is_visible_memory_for_retrieval(memory, include_candidates=include_candidates) is False:
                    continue
                if not include_lessons and _is_lesson_memory(memory):
                    continue
                dk = _retrieval_dedup_key(memory)
                vs = vector_scores.get(memory_id, 0.0)
                if dk in seen_dedup and vs <= seen_dedup[dk]:
                    continue
                seen_dedup[dk] = vs

                content = str(memory["content"])
                keyword_score = self._keyword_overlap(self._tokens(query), self._tokens(content))
                importance_score = float(memory.get("importance_score", 0.0))
                final_score = (
                    vs * weights["semantic"]
                    + keyword_score * weights["keyword"]
                    + self._temporal_score(str(memory.get("valid_from") or memory.get("updated_at") or ""), now) * weights["temporal"]
                    + self._entity_overlap(self._tokens(query), memory.get("entities_json", "[]")) * weights["entity"]
                    + importance_score * weights["importance"]
                    + (0.15 if str(memory.get("memory_type", "")) == "EPISODIC" else 0.0) * weights["episodic"]
                )
                final_score += _layer_score_boost(memory)
                results.append(RetrievalResult(
                    memory_id=memory_id, content=content,
                    memory_type=str(memory.get("memory_type", "")),
                    scope=str(memory.get("scope", "global")),
                    semantic_score=vs, keyword_score=keyword_score,
                    temporal_score=0.0, entity_score=0.0,
                    importance_score=importance_score, episodic_score=0.0,
                    final_score=final_score, explanation="fallback_fetch",
                ))

        results.sort(key=lambda item: item.final_score, reverse=True)

        # 24.4-B: min score threshold trimming (only when results > limit)
        if len(results) > limit:
            results = [r for r in results if r.final_score >= MIN_FINAL_SCORE]
            if not results:
                results = []  # empty is safe

        # LESSON fusion: boost matching lesson memories
        if include_lessons:
            results = await self._merge_lesson_candidates(
                results,
                query=query,
                intent=str(intent.value) if intent else None,
                session_id=session_id,
                scope_filter=scope_filter,
                include_global=include_global,
                limit=limit,
            )

        results = results[:limit]

        if explain_scores:
            trace = RetrievalTrace(
                query_plan_used=fts_trace.get("query_plan_used"),
                fallback_steps=fts_trace.get("fallback_steps", []),
                fallback_used=fallback_used,
                vector_available=vector_available,
                raw_hits=raw_hit_count,
                visible_hits=len(results),
                dedup_dropped=dedup_dropped,
                hidden_candidates=hidden_candidates,
                hidden_session=hidden_session,
                hidden_lessons=hidden_lessons,
                hidden_state=hidden_state,
                layer_boost_applied=layer_boost_applied,
                fetch_limit=base_fetch,
                fallback_fetch_limit=fallback_fetch if fallback_used else None,
            )
            return results, trace.to_dict()

        return results

    @staticmethod
    def _build_visibility_filter(
        *,
        session_id: str | None,
        scope_filter: str | None,
        include_global: bool = True,
        session_only: bool = False,
    ) -> tuple[str, list[Any]]:
        """Build WHERE clause for session/scope visibility filtering."""
        clauses = ["active_state = 'active'"]
        params: list[Any] = []

        visible: list[str] = []

        if session_only:
            # Broad SQL pass — don't filter on scope here. The final eligibility
            # is enforced in the memory loop via _is_session_scoped_memory().
            # This avoids false negatives for scope='global' + memory_layer='session'.
            if session_id:
                visible.append("session_id = ?")
                params.append(session_id)
            elif visible:
                visible.append("1=0")
            clauses.append("(" + " OR ".join(visible) + ")")
            return " AND ".join(clauses), params

        if session_id:
            visible.append("session_id = ?")
            params.append(session_id)

        if scope_filter:
            visible.append("scope = ?")
            params.append(scope_filter)
        elif not session_id:
            # No session isolation — unfiltered
            if not scope_filter:
                return " AND ".join(clauses), params

        if include_global:
            visible.append("scope = 'global'")

        if visible:
            clauses.append("(" + " OR ".join(visible) + ")")

        return " AND ".join(clauses), params

    def _intent_weights(self, intent: RetrievalIntent | None) -> dict[str, float]:
        base = {
            "semantic": 0.25,
            "keyword": 0.25,
            "temporal": 0.15,
            "entity": 0.10,
            "importance": 0.15,
            "episodic": 0.10,
        }
        if intent is None:
            return base

        overrides = {
            RetrievalIntent.CODING: {"keyword": 0.35, "entity": 0.20, "semantic": 0.20, "temporal": 0.05},
            RetrievalIntent.DEBUGGING: {"temporal": 0.30, "keyword": 0.25, "episodic": 0.20},
            RetrievalIntent.DEPLOYMENT: {"temporal": 0.25, "episodic": 0.25},
            RetrievalIntent.TROUBLESHOOTING: {"episodic": 0.25, "keyword": 0.30},
            RetrievalIntent.PREFERENCE: {"importance": 0.25, "semantic": 0.30},
            RetrievalIntent.PROJECT: {"entity": 0.25, "importance": 0.20},
            RetrievalIntent.WORKFLOW: {"episodic": 0.30, "entity": 0.15},
        }
        result = dict(base)
        result.update(overrides.get(intent, {}))
        return result

    @staticmethod
    def _tokens(text: str) -> set[str]:
        return set("".join(ch.lower() if ch.isalnum() else " " for ch in text).split())

    @staticmethod
    def _keyword_overlap(query_tokens: set[str], content_tokens: set[str]) -> float:
        if not query_tokens:
            return 0.0
        return len(query_tokens & content_tokens) / len(query_tokens)

    @staticmethod
    def _entity_overlap(query_tokens: set[str], entities_json: str) -> float:
        import json
        try:
            entities = json.loads(entities_json or "[]")
        except (ValueError, TypeError):
            return 0.0
        if not entities:
            return 0.0
        entity_tokens = set("".join(ch.lower() if ch.isalnum() else " " for ch in str(e)).split() for e in entities)
        hits = sum(1 for t in query_tokens if any(t in e for e in entity_tokens))
        return hits / len(query_tokens) if query_tokens else 0.0

    @staticmethod
    def _temporal_score(valid_from_or_updated: str, now: datetime) -> float:
        if not valid_from_or_updated:
            return 0.5
        try:
            dt = datetime.fromisoformat(valid_from_or_updated.replace("Z", "+00:00"))
            delta_hours = max(0.0, (now - dt).total_seconds() / 3600.0)
            return max(0.0, 1.0 - delta_hours / 720.0)  # decay over 30 days
        except (ValueError, OverflowError):
            return 0.5

    @staticmethod
    def _match_tags(tags_json: str, filters: list[str], mode: str) -> bool:
        import json
        try:
            tags = [t.lower() for t in json.loads(tags_json or "[]")]
        except (ValueError, TypeError):
            return True
        filter_lower = [f.lower() for f in filters]
        if mode == "all":
            return all(f in tags for f in filter_lower)
        return any(f in tags for f in filter_lower)

    def _build_explanation(
        self,
        semantic_score: float,
        keyword_score: float,
        temporal_score: float,
        entity_score: float,
        importance_score: float,
        episodic_score: float,
        intent: RetrievalIntent | None = None,
    ) -> str:
        parts = [
            f"semantic={semantic_score:.2f}",
            f"keyword={keyword_score:.2f}",
            f"temporal={temporal_score:.2f}",
            f"entity={entity_score:.2f}",
            f"importance={importance_score:.2f}",
            f"episodic={episodic_score:.2f}",
        ]
        if intent:
            parts.append(f"intent={intent.value}")
        return ", ".join(parts)

    # ── LESSON retrieval boost ──

    async def _merge_lesson_candidates(
        self,
        results: list[RetrievalResult],
        *,
        query: str,
        intent: str | None,
        session_id: str | None,
        scope_filter: str | None,
        include_global: bool,
        limit: int,
    ) -> list[RetrievalResult]:
        from memoryx.cognitive.lessons import LessonPolicyEngine
        engine = LessonPolicyEngine(repository=self.repository)
        lessons = await engine.match(
            query=query,
            intent=intent,
            session_id=session_id,
            scope_filter=scope_filter,
            include_global=include_global,
            limit=max(5, limit),
        )
        if not lessons:
            return results

        by_id = {r.memory_id: r for r in results}
        for lesson in lessons:
            mid = lesson["memory_id"]
            match_score = float(lesson.get("lesson_match_score", 0.0))
            boost = 0.35 + 0.55 * match_score

            if mid in by_id:
                item = by_id[mid]
                item.final_score = item.final_score + boost
                item.explanation = item.explanation + f", lesson_boost={boost:.2f}"
                continue

            item = self._lesson_to_retrieval_result(lesson, boost=boost)
            results.append(item)

        results.sort(key=lambda r: r.final_score, reverse=True)
        return results[:limit]

    @staticmethod
    def _lesson_to_retrieval_result(lesson: dict, *, boost: float) -> RetrievalResult:
        mid = lesson.get("memory_id", "")
        return RetrievalResult(
            memory_id=mid,
            content=lesson.get("lesson_text") or lesson.get("content", ""),
            memory_type="LESSON",
            scope=lesson.get("scope", "global"),
            semantic_score=0.0,
            keyword_score=float(lesson.get("lesson_match_score", 0.0)),
            temporal_score=0.0,
            entity_score=0.0,
            importance_score=float(lesson.get("severity", 0.0)),
            episodic_score=0.0,
            final_score=min(1.0, 0.60 + boost),
            explanation=f"lesson_boost={boost:.2f},"
            f"match={lesson.get('lesson_match_score',0):.2f},"
            f"policy={lesson.get('policy_type','')}",
        )
