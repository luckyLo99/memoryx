"""MemoryRecord dataclass — extracted from repository.py to reduce file size.

P0 schema: memories.id PK, not memory_id.
Legacy/public alias: ``memory_id`` is accepted in constructor and
exposed as a read-only property returning ``self.id``.
When both ``id`` and ``memory_id`` are supplied, ``id`` wins.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4


@dataclass(init=False)
class MemoryRecord:
    id: str
    session_id: str | None = None
    memory_type: str = "FACT"
    content: str = ""
    content_summary: str | None = None
    content_hash: str = ""
    checksum: str = ""
    importance_score: float = 0.0
    confidence_score: float = 0.0
    decay_score: float = 0.0
    recency_score: float = 0.0
    access_count: int = 0
    reinforcement_score: float = 0.0
    safety_score: float = 1.0
    active_state: str = "active"
    superseded_by: str | None = None
    contradiction_group_id: str | None = None
    valid_from: str = ""
    valid_to: str | None = None
    archived_at: str | None = None
    metadata_json: str = "{}"

    def __init__(
        self,
        id: str | None = None,
        memory_id: str | None = None,
        session_id: str | None = None,
        memory_type: str = "FACT",
        content: str = "",
        content_summary: str | None = None,
        content_hash: str = "",
        checksum: str = "",
        importance_score: float = 0.0,
        confidence_score: float = 0.0,
        decay_score: float = 0.0,
        recency_score: float = 0.0,
        access_count: int = 0,
        reinforcement_score: float = 0.0,
        safety_score: float = 1.0,
        active_state: str = "active",
        superseded_by: str | None = None,
        contradiction_group_id: str | None = None,
        valid_from: str = "",
        valid_to: str | None = None,
        archived_at: str | None = None,
        metadata_json: str = "{}",
        scope: str = "global",
        tags_json: str = "[]",
        entities_json: str = "[]",
        source_message_id: str | None = None,
    ) -> None:
        if id is None and memory_id is not None:
            id = memory_id
        if id is None:
            id = uuid4().hex
        self.id = id
        self.session_id = session_id
        self.memory_type = memory_type
        self.content = content
        self.content_summary = content_summary
        self.content_hash = content_hash
        self.checksum = checksum
        self.importance_score = importance_score
        self.confidence_score = confidence_score
        self.decay_score = decay_score
        self.recency_score = recency_score
        self.access_count = access_count
        self.reinforcement_score = reinforcement_score
        self.safety_score = safety_score
        self.active_state = active_state
        self.superseded_by = superseded_by
        self.contradiction_group_id = contradiction_group_id
        self.valid_from = valid_from
        self.valid_to = valid_to
        self.archived_at = archived_at
        self.metadata_json = metadata_json
        self.scope = scope
        self.tags_json = tags_json
        self.entities_json = entities_json
        self.source_message_id = source_message_id

    @property
    def memory_id(self) -> str:
        """Legacy public alias — always returns self.id."""
        return self.id