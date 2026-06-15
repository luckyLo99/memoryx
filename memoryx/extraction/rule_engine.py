"""Offline rule-based memory extraction (no LLM required).

Used as a graceful fallback when LLM API is unavailable or
MEMORYX_LLM_ENABLED=false.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from .models import ExtractionMemory, ExtractionRequest, ExtractionResult, ExtractionSource


# Simple pattern-based extraction rules
_EXTRACTION_PATTERNS: list[tuple[str, str, float, float]] = [
    # (regex, memory_type, importance, confidence)
    (r"my name is\s+(.+?)(?:\.|$)", "FACT", 0.9, 0.95),
    (r"i am\s+(.+?)(?:\.|$)", "FACT", 0.7, 0.8),
    (r"i work at\s+(.+?)(?:\.|$)", "FACT", 0.8, 0.9),
    (r"i work as\s+(?:a|an)\s+(.+?)(?:\.|$)", "FACT", 0.8, 0.9),
    (r"i live in\s+(.+?)(?:\.|$)", "FACT", 0.7, 0.85),
    (r"i live at\s+(.+?)(?:\.|$)", "FACT", 0.7, 0.85),
    (r"i prefer\s+(.+?)(?:\.|$)", "PREFERENCE", 0.8, 0.85),
    (r"i like\s+(.+?)(?:\.|$)", "PREFERENCE", 0.7, 0.8),
    (r"i love\s+(.+?)(?:\.|$)", "PREFERENCE", 0.75, 0.8),
    (r"i enjoy\s+(.+?)(?:\.|$)", "PREFERENCE", 0.7, 0.8),
    (r"i hate\s+(.+?)(?:\.|$)", "PREFERENCE", 0.75, 0.8),
    (r"i dislike\s+(.+?)(?:\.|$)", "PREFERENCE", 0.75, 0.8),
    (r"i don't like\s+(.+?)(?:\.|$)", "PREFERENCE", 0.7, 0.8),
    (r"i want\s+(.+?)(?:\.|$)", "PREFERENCE", 0.6, 0.7),
    (r"i need\s+(.+?)(?:\.|$)", "TASK", 0.6, 0.7),
    (r"i should\s+(.+?)(?:\.|$)", "TASK", 0.6, 0.7),
    (r"i must\s+(.+?)(?:\.|$)", "TASK", 0.65, 0.75),
    (r"i have to\s+(.+?)(?:\.|$)", "TASK", 0.6, 0.7),
    (r"my favorite\s+(.+?)\s+is\s+(.+?)(?:\.|$)", "PREFERENCE", 0.85, 0.9),
    (r"i use\s+(.+?)(?:\.|$)", "PREFERENCE", 0.65, 0.75),
    (r"project\s+(.+?)\s+is\s+(.+?)(?:\.|$)", "PROJECT", 0.7, 0.8),
    (r"we are building\s+(.+?)(?:\.|$)", "PROJECT", 0.75, 0.8),
    (r"the goal is\s+(.+?)(?:\.|$)", "PROJECT", 0.7, 0.75),
    (r"deadline is\s+(.+?)(?:\.|$)", "TASK", 0.8, 0.85),
    (r"due date is\s+(.+?)(?:\.|$)", "TASK", 0.8, 0.85),
]

_ENTITY_PATTERNS = [
    (r"\b[A-Z][a-z]+\b", "person"),
    (r"\b[A-Z][a-zA-Z]*\d+\b", "identifier"),
]


def _extract_entities(text: str) -> list[str]:
    """Extract simple entities from text."""
    entities: set[str] = set()
    for pattern, _ in _ENTITY_PATTERNS:
        for match in re.finditer(pattern, text):
            word = match.group(0)
            if len(word) > 2 and word.lower() not in {
                "the", "and", "but", "for", "are", "with", "his", "her",
                "was", "were", "been", "have", "has", "had", "you", "she",
                "they", "this", "that", "from", "they", "them", "their",
            }:
                entities.add(word)
    return sorted(entities)[:10]


def _extract_tags(text: str) -> list[str]:
    """Extract simple tags from text."""
    tags: set[str] = set()
    lower = text.lower()
    tag_keywords = {
        "python": "python", "rust": "rust", "javascript": "javascript",
        "typescript": "typescript", "java": "java", "go": "go",
        "docker": "docker", "kubernetes": "kubernetes", "k8s": "kubernetes",
        "aws": "aws", "azure": "azure", "gcp": "gcp",
        "frontend": "frontend", "backend": "backend", "fullstack": "fullstack",
        "database": "database", "api": "api", "testing": "testing",
        "deployment": "deployment", "ci/cd": "cicd", "git": "git",
        "sql": "sql", "nosql": "nosql", "postgres": "postgresql",
        "sqlite": "sqlite", "redis": "redis", "mongodb": "mongodb",
    }
    for keyword, tag in tag_keywords.items():
        if keyword in lower:
            tags.add(tag)
    return sorted(tags)[:5]


class RuleExtractionEngine:
    """Extract memories using rule-based patterns (no LLM required)."""

    def __init__(self, min_importance: float = 0.3, min_confidence: float = 0.4) -> None:
        self.min_importance = min_importance
        self.min_confidence = min_confidence

    def extract(self, request: ExtractionRequest) -> ExtractionResult:
        memories: list[ExtractionMemory] = []
        for source in request.sources:
            memories.extend(self._extract_from_source(source, request.session_id))
        filtered = [
            m for m in memories
            if m.importance_score >= self.min_importance
            and m.confidence_score >= self.min_confidence
        ]
        return ExtractionResult(memories=filtered)

    def _extract_from_source(self, source: ExtractionSource, session_id: str | None) -> list[ExtractionMemory]:
        text = source.content or ""
        if not text.strip():
            return []

        results: list[ExtractionMemory] = []
        now = datetime.now(timezone.utc).isoformat()

        for pattern, mem_type, importance, confidence in _EXTRACTION_PATTERNS:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                content = match.group(0).strip()
                if not content:
                    continue
                entities = _extract_entities(text)
                tags = _extract_tags(text)
                results.append(ExtractionMemory(
                    memory_type=mem_type,
                    content=content,
                    importance_score=importance,
                    confidence_score=confidence,
                    entities=entities,
                    tags=tags,
                    scope="global",
                    timestamp=now,
                    source_message_id=source.source_message_id,
                    reasoning=f"rule_extract: matched pattern '{pattern[:40]}...'",
                ))

        # Deduplicate by content
        seen: set[str] = set()
        unique: list[ExtractionMemory] = []
        for m in results:
            key = m.content.lower()
            if key not in seen:
                seen.add(key)
                unique.append(m)

        return unique
