from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any, TYPE_CHECKING

from memoryx.extraction import ExtractionMemory

if TYPE_CHECKING:
    from memoryx.evolution.integration import EvolutionIntegration, IntegrationDecision


@dataclass(slots=True)
class ConflictMatch:
    conflicting_memory: ExtractionMemory
    reason: str
    similarity_score: float | None = None


def _memory_id(memory: ExtractionMemory) -> str:
    """为 ExtractionMemory 生成唯一标识（基于 content + timestamp）。"""
    key = f"{memory.content}|{memory.timestamp.isoformat()}"
    return hashlib.md5(key.encode()).hexdigest()[:12]


class ConflictResolver:
    """P0: 升级语义冲突检测 — 结合 embedding 相似度 + 关键词规则。

    检测策略（两级）：
    1. 语义相似度检测：candidate 与现有记忆 embedding 相似度 > 阈值 → 进入冲突检查
    2. 关键词矛盾检测：正反情感标记互斥 → 确认冲突

    优势：
    - 避免关键词误报（如 "I don't dislike" 实际是正面）
    - 能检测同义但矛盾的表达（"喜欢咖啡" vs "咖啡不好喝"）

    Evolution-aware flow:
    When an ``EvolutionIntegration`` instance is supplied, the resolver first
    checks whether the incoming content represents a *preference change* (e.g.
    "my favorite singer is now X").  If it does, the content is routed through
    the evolution pipeline (``EvolutionIntegration.route``) and the resolver
    returns **no conflict** — the change is an evolutionary append, not a
    contradiction.  If the content is *not* a preference signal, or if
    ``evolution_integration`` is ``None`` (the default), the resolver falls
    through to the existing two-level conflict detection logic unchanged.
    """

    # ── 情感/否定标记（增强版） ─────────────────────────────────────
    NEGATIVE_MARKERS = (
        "dislike", "dislikes", "disliked", "hate", "hates", "hated",
        "not", "no", "never", "no longer", "not anymore",
        "opposite", "ignore", "ignored", "avoid", "avoiding",
        "disagree", "disagrees", "wrong", "incorrect", "bad",
        "terrible", "awful", "poor", "worst", "cannot", "can't",
        "won't", "do not", "does not", "did not", "is not", "are not",
        "was not", "were not", "has not", "have not", "had not",
        "hates", "hating", "disliking",
    )
    POSITIVE_MARKERS = (
        "like", "likes", "liked", "liking", "prefer", "prefers",
        "love", "loves", "loving", "use", "uses", "using",
        "want", "wants", "wanting", "choose", "chooses", "choosing",
        "good", "great", "excellent", "best", "enjoy", "enjoys",
        "enjoying", "happy", "happiness", "pleased", "satisfied",
        "agree", "agrees", "agreeing", "correct", "right",
    )

    # ── 同义/反义对（用于更精确的冲突检测） ─────────────────────────
    ANTONYM_PAIRS = [
        ("like", "dislike"),
        ("like", "hate"),
        ("love", "hate"),
        ("prefer", "avoid"),
        ("agree", "disagree"),
        ("use", "ignore"),
        ("want", "avoid"),
        ("choose", "reject"),
        ("good", "bad"),
        ("best", "worst"),
        ("happy", "sad"),
        ("enjoy", "dislike"),
        ("satisfied", "disappointed"),
    ]

    # ── 冲突检测 ────────────────────────────────────────────────────

    def decide_evolution(
        self,
        candidate_content: str,
        entity_id: str,
        evolution_integration: EvolutionIntegration | None = None,
    ) -> IntegrationDecision | None:
        """Check whether the candidate content is a preference evolution event.

        Args:
            candidate_content: The text content of the candidate memory.
            entity_id: The entity this memory belongs to.
            evolution_integration: Optional ``EvolutionIntegration`` instance.

        Returns:
            * ``None`` — no evolution integration provided, or the content is
              not a preference change.  The caller should proceed with normal
              conflict detection.
            * ``IntegrationDecision`` — the content *is* a preference change
              and has been routed through the evolution pipeline.  The caller
              can inspect ``is_evolution`` to decide whether to skip conflict
              detection.
        """
        if evolution_integration is None:
            return None

        if not evolution_integration.is_preference_change(candidate_content):
            return None

        # Detect signals and route the first one through the evolution pipeline
        signals = evolution_integration.manager.detector.detect(
            candidate_content, entity_id=entity_id
        )
        change_signals = [s for s in signals if s.is_change]
        if not change_signals:
            return None

        return evolution_integration.route(change_signals[0])

    def resolve(
        self,
        candidate: ExtractionMemory,
        existing_memories: list[ExtractionMemory],
        *,
        semantic_threshold: float = 0.7,
        vector_store: Any | None = None,
        evolution_integration: EvolutionIntegration | None = None,
    ) -> ConflictMatch | None:
        """检测 candidate 与现有记忆的冲突。

        When *evolution_integration* is supplied, the method first checks
        whether the candidate represents a preference evolution event.  If
        ``decide_evolution`` returns an ``IntegrationDecision`` with
        ``is_evolution=True``, no conflict is reported (the change is treated
        as an evolutionary append).  Otherwise, normal conflict detection
        proceeds.

        Args:
            candidate: 待检测的新记忆
            existing_memories: 现有记忆列表
            semantic_threshold: embedding 语义相似度阈值（0-1）
            vector_store: 可选的向量存储，用于语义相似度计算
            evolution_integration: 可选的 EvolutionIntegration 实例

        Returns:
            ConflictMatch 如果检测到冲突，否则 None
        """
        # ── Evolution-aware check ────────────────────────────────────
        evo_decision = self.decide_evolution(
            candidate.content,
            entity_id="user",
            evolution_integration=evolution_integration,
        )
        if evo_decision is not None and evo_decision.is_evolution:
            return None  # evolutionary append — not a conflict

        # ── Existing conflict detection logic ────────────────────────
        candidate_text = candidate.content.lower()
        candidate_reasoning = (candidate.reasoning or "").lower()
        candidate_combined = candidate_text + " " + candidate_reasoning

        # 使用语义搜索（关键词匹配或向量搜索）预筛选
        similar = self._semantic_search_sync(
            vector_store, candidate_combined, existing_memories, top_k=10
        )
        candidates_to_check = similar if similar else existing_memories

        for memory in candidates_to_check:
            text = memory.content.lower()
            reasoning = (memory.reasoning or "").lower()
            combined = text + " " + reasoning

            # 先检查关键词矛盾
            keyword_conflict = self._is_contradiction(candidate_combined, combined)
            if not keyword_conflict:
                continue

            # 再检查语义相似度（确认是否真的在说同一件事）
            similarity = None
            if vector_store is not None and hasattr(vector_store, "search_sync"):
                similarity = self._compute_similarity_sync(
                    vector_store, candidate_combined, _memory_id(memory)
                )

            # 语义相似度 > 阈值 或 关键词强矛盾 → 确认冲突
            if similarity is not None and similarity >= semantic_threshold:
                return ConflictMatch(
                    conflicting_memory=memory,
                    reason=f"语义冲突（相似度={similarity:.2f}，超过阈值{semantic_threshold}）",
                    similarity_score=similarity,
                )
            elif keyword_conflict:
                return ConflictMatch(
                    conflicting_memory=memory,
                    reason="contradiction detected: polarity markers conflict (positive vs negative)",
                    similarity_score=similarity,
                )

        return None

    def _is_contradiction(self, a: str, b: str) -> bool:
        """增强版关键词矛盾检测。"""
        # 1. 检查反义对冲突（使用单词边界避免误匹配）
        for pos, neg in self.ANTONYM_PAIRS:
            pos_pattern = re.compile(rf"\b{re.escape(pos)}\b")
            neg_pattern = re.compile(rf"\b{re.escape(neg)}\b")
            
            a_has_pos = pos_pattern.search(a) is not None
            a_has_neg = neg_pattern.search(a) is not None
            b_has_pos = pos_pattern.search(b) is not None
            b_has_neg = neg_pattern.search(b) is not None
            
            if (a_has_pos and b_has_neg) or (a_has_neg and b_has_pos):
                return True

        # 2. 检查否定标记 vs 肯定标记（使用单词边界）
        has_neg_a = any(re.search(rf"\b{re.escape(m)}\b", a) for m in self.NEGATIVE_MARKERS)
        has_pos_a = any(re.search(rf"\b{re.escape(m)}\b", a) for m in self.POSITIVE_MARKERS)
        has_neg_b = any(re.search(rf"\b{re.escape(m)}\b", b) for m in self.NEGATIVE_MARKERS)
        has_pos_b = any(re.search(rf"\b{re.escape(m)}\b", b) for m in self.POSITIVE_MARKERS)

        if (has_neg_a and has_pos_b) or (has_neg_b and has_pos_a):
            return True

        # 3. 检查否定词修饰同一关键词（如 "not like" vs "like"）
        for marker in self.POSITIVE_MARKERS:
            marker_pattern = re.compile(rf"\b{re.escape(marker)}\b")
            not_marker_pattern = re.compile(rf"\bnot {re.escape(marker)}\b")
            
            if marker_pattern.search(a) and not_marker_pattern.search(b):
                return True
            if marker_pattern.search(b) and not_marker_pattern.search(a):
                return True

        return False

    # ── 语义相似度（同步版本，依赖外部 vector_store） ────────────────

    def _semantic_search_sync(
        self, vector_store: Any, query: str, existing_memories: list[ExtractionMemory], top_k: int = 10
    ) -> list[ExtractionMemory]:
        """在 vector_store 中搜索语义相似的记忆，或使用关键词匹配作为 fallback。"""
        try:
            if vector_store is not None and hasattr(vector_store, "search_sync"):
                results = vector_store.search_sync(query, limit=top_k)
                # 尝试将结果映射回 existing_memories
                memory_map = {_memory_id(m): m for m in existing_memories}
                matched = []
                for result in results:
                    memory_id = result.get("memory_id") or result.get("claim_id")
                    if memory_id and memory_id in memory_map:
                        matched.append(memory_map[memory_id])
                if matched:
                    return matched[:top_k]
        except Exception:
            pass
        
        # Fallback: 简单关键词匹配
        query_lower = query.lower()
        scored = []
        for memory in existing_memories:
            combined = (memory.content + " " + (memory.reasoning or "")).lower()
            # 计算简单的关键词重叠分数
            score = 0.0
            query_words = set(query_lower.split())
            combined_words = set(combined.split())
            if query_words:
                overlap = len(query_words & combined_words)
                score = overlap / len(query_words)
            if score > 0:
                scored.append((score, memory))
        
        # 按分数排序并返回 top_k
        scored.sort(reverse=True, key=lambda x: x[0])
        return [memory for _, memory in scored[:top_k]]

    def _compute_similarity_sync(
        self, vector_store: Any, query: str, memory_id: str
    ) -> float | None:
        """计算 query 与指定记忆 ID 的余弦相似度。"""
        try:
            results = vector_store.search_sync(query, limit=1)
            for r in results:
                if r.get("id") == memory_id:
                    return r.get("score") or 0.0
            return None
        except Exception:
            return None
