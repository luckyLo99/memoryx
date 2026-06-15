from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import datetime, timezone
from typing import Any, Protocol

from .models import ExtractionMemory, ExtractionRequest, ExtractionResult, ExtractionSource

logger = logging.getLogger(__name__)


class ExtractionClient(Protocol):
    async def extract(self, request: ExtractionRequest) -> dict: ...


class MemoryExtractionEngine:
    def __init__(self, client: ExtractionClient | None = None, batch_size: int = 8,
                 min_importance: float = 0.3, min_confidence: float = 0.4,
                 llm_enabled: bool = True) -> None:
        self.client = client
        self.batch_size = batch_size
        self.min_importance = min_importance
        self.min_confidence = min_confidence
        self.llm_enabled = llm_enabled
        self._rule_engine: Any | None = None

    async def extract(self, request: ExtractionRequest) -> ExtractionResult:
        if not self.llm_enabled or self.client is None:
            return self._rule_extract(request)
        all_memories: list[ExtractionMemory] = []
        for batch in self._batched(request.sources):
            try:
                payload = await self.client.extract(ExtractionRequest(session_id=request.session_id, sources=batch))
            except (ConnectionError, TimeoutError, OSError) as e:
                logger.warning("LLM extraction network error, falling back to rule-based: %s", e)
                rule_result = self._rule_extract(ExtractionRequest(session_id=request.session_id, sources=batch))
                all_memories.extend(rule_result.memories)
                continue
            except Exception:
                logger.warning("LLM extraction failed, falling back to rule-based extraction", exc_info=True)
                rule_result = self._rule_extract(ExtractionRequest(session_id=request.session_id, sources=batch))
                all_memories.extend(rule_result.memories)
                continue
            all_memories.extend(self._normalize_payload(payload))
        filtered = [
            memory
            for memory in all_memories
            if memory.importance_score >= self.min_importance and memory.confidence_score >= self.min_confidence
        ]
        return ExtractionResult(memories=filtered)

    def _rule_extract(self, request: ExtractionRequest) -> ExtractionResult:
        """Fallback to rule-based extraction when LLM is disabled."""
        if self._rule_engine is None:
            from .rule_engine import RuleExtractionEngine
            self._rule_engine = RuleExtractionEngine(
                min_importance=self.min_importance,
                min_confidence=self.min_confidence,
            )
        return self._rule_engine.extract(request)

    def _batched(self, sources: list[ExtractionSource]) -> Iterable[list[ExtractionSource]]:
        for index in range(0, len(sources), self.batch_size):
            yield sources[index : index + self.batch_size]

    def _normalize_payload(self, payload: dict) -> list[ExtractionMemory]:
        result: list[ExtractionMemory] = []
        for item in payload.get("memories", []):
            try:
                if "timestamp" not in item or not item["timestamp"]:
                    item = {**item, "timestamp": datetime.now(timezone.utc).isoformat()}
                result.append(ExtractionMemory.model_validate(item))
            except (ValueError, TypeError, KeyError) as e:
                logger.warning("Skipping invalid extraction memory item: %s — %s", item, e)
            except Exception:
                logger.warning("Skipping invalid extraction memory item: %s", item, exc_info=True)
        return result
