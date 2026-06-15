"""Dual-process retrieval: System 1 (fast) vs System 2 (slow) retrieval.

Based on Kahneman (2011) Thinking, Fast and Slow:
- System 1: Fast, automatic, intuitive, low-effort
- System 2: Slow, deliberate, analytical, high-effort

Retrieval gating: queries below complexity threshold use System 1;
complex/ambiguous queries escalate to System 2.
System 2 also activates when System 1 confidence is low.

References:
- Kahneman, D. (2011). Thinking, Fast and Slow.
- Evans, J. St. B. T. (2008). Dual-processing accounts of reasoning.
- Pennycook, G. (2017). A perspective on the theoretical foundation of dual process models.
"""

from __future__ import annotations

import re
from time import perf_counter
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class RetrievalSystem(Enum):
    SYSTEM_1 = "system_1"
    SYSTEM_2 = "system_2"


@dataclass
class RetrievalDecision:
    system: RetrievalSystem = RetrievalSystem.SYSTEM_1
    complexity_score: float = 0.0
    confidence_threshold: float = 0.6
    reason: str = ""
    escalation_chain: list[str] = field(default_factory=list)
    processing_time_ms: float = 0.0


class QueryComplexityAnalyzer:
    COMPLEX_PATTERNS = [
        r"\b(?:why|how|explain|compare|contrast|analyze|evaluate|what if)\b",
        r"\b(?:architecture|design|pattern|strategy|migration|refactor)\b",
        r"\b(?:root.cause|regression|vulnerability|security)\b",
        r"\b(?:relationship|connection|depend|correlation|influence)\b",
        r"\?$",
    ]

    @staticmethod
    def analyze(query: str) -> float:
        q = query.lower().strip()
        if not q:
            return 0.0
        word_count = len(q.split())
        pattern_hits = sum(1 for p in QueryComplexityAnalyzer.COMPLEX_PATTERNS if re.search(p, q))
        complexity = 0.0
        if word_count > 15:
            complexity += 0.3
        if word_count > 30:
            complexity += 0.2
        complexity += 0.20 * min(pattern_hits, 4)
        if q.endswith("?"):
            complexity += 0.10
        return min(1.0, complexity)

    @staticmethod
    def classify(complexity: float) -> RetrievalSystem:
        if complexity >= 0.35:
            return RetrievalSystem.SYSTEM_2
        return RetrievalSystem.SYSTEM_1


class System1Retriever:
    def __init__(self, fts_retriever: Any = None, cache: dict | None = None):
        self.fts_retriever = fts_retriever
        self.cache = cache or {}

    async def search(self, query: str, limit: int = 5) -> list[dict]:
        cached = self.cache.get(query)
        if cached is not None:
            return cached[:limit]
        if self.fts_retriever is not None:
            results = await self.fts_retriever(query, limit=limit)
            self.cache[query] = results
            return results
        return []


class System2Retriever:
    def __init__(self, hybrid_engine: Any = None, conflict_detector: Any = None):
        self.hybrid_engine = hybrid_engine
        self.conflict_detector = conflict_detector

    async def search(self, query: str, limit: int = 10, session_id: str | None = None) -> list[dict]:
        results = []
        if self.hybrid_engine is not None:
            results = await self.hybrid_engine(query, limit=limit, session_id=session_id)
        if self.conflict_detector is not None and results:
            try:
                conflicts = await self.conflict_detector.detect(results)
                for r in results:
                    r["_conflicts"] = conflicts.get(r.get("memory_id", ""), [])
            except Exception:
                pass
        return results


class DualProcessGateway:
    def __init__(self, system1: System1Retriever, system2: System2Retriever,
                 confidence_threshold: float = 0.6):
        self.system1 = system1
        self.system2 = system2
        self.confidence_threshold = confidence_threshold
        self.analyzer = QueryComplexityAnalyzer()
        self.stats = {"s1_calls": 0, "s2_calls": 0, "escalations": 0}

    async def retrieve(self, query: str, limit: int = 10,
                      session_id: str | None = None) -> tuple[list[dict], RetrievalDecision]:
        t0 = perf_counter()
        complexity = self.analyzer.analyze(query)
        system = self.analyzer.classify(complexity)
        decision = RetrievalDecision(
            system=system, complexity_score=complexity,
            reason=f"complexity={complexity:.2f}"
        )

        if system == RetrievalSystem.SYSTEM_1:
            self.stats["s1_calls"] += 1
            results = await self.system1.search(query, limit=limit)
            confidence = self._estimate_confidence(results, query)
            if confidence < self.confidence_threshold:
                decision.escalation_chain.append("s1_low_confidence")
                self.stats["escalations"] += 1
                self.stats["s2_calls"] += 1
                results = await self.system2.search(query, limit=limit * 2, session_id=session_id)
                decision.system = RetrievalSystem.SYSTEM_2
                decision.reason += f"->escalated(confidence={confidence:.2f})"
        else:
            self.stats["s2_calls"] += 1
            results = await self.system2.search(query, limit=limit * 2, session_id=session_id)

        decision.processing_time_ms = (perf_counter() - t0) * 1000
        return results, decision

    @staticmethod
    def _estimate_confidence(results: list[dict], query: str) -> float:
        if not results:
            return 0.0
        scores = [float(r.get("final_score", r.get("score", 0.0))) for r in results]
        if not scores:
            return 0.0
        max_score = max(scores)
        coverage = 0.3 if any(qw.lower() in str(r.get("content", "")).lower()
                         for r in results for qw in query.split()) else 0.0
        return min(1.0, max_score * 0.7 + coverage * 0.3)

    def get_stats(self) -> dict[str, int]:
        return dict(self.stats)

    def reset_stats(self) -> None:
        self.stats = {"s1_calls": 0, "s2_calls": 0, "escalations": 0}
