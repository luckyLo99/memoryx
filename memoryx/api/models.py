"""Shared Pydantic request models for the MemoryX REST API.

Models defined here are used by multiple route modules to avoid duplication.
"""

from __future__ import annotations

from pydantic import BaseModel


# ── Task lifecycle request models (shared by memories.py and routes/tasks.py) ──

class TaskStartRequest(BaseModel):
    session_id: str = "default"
    entity_id: str = "general"
    task_type: str = "conversation"
    title: str = "Hermes session"
    source: str = "hermes"


class TaskEndRequest(BaseModel):
    session_id: str = "default"
    entity_id: str = "general"
    status: str = "done"
    summary: str = ""
    source: str = "hermes"


class TaskDurationsQuery(BaseModel):
    session_id: str | None = None
    entity_id: str | None = None
    task_type: str | None = None
    since: str | None = None
    until: str | None = None


class EntityTimelineQuery(BaseModel):
    entity_id: str = "general"
    since: str | None = None
    until: str | None = None
    limit: int = 50