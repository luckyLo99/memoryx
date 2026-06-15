from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

JSONSchema = dict[str, Any]

@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: JSONSchema
    read_only: bool = False
    destructive: bool = False

@dataclass(frozen=True)
class ToolCallResult:
    ok: bool
    data: Any = None
    error: str | None = None
    tool_name: str | None = None
    trace: dict[str, Any] = field(default_factory=dict)

def object_schema(properties: dict[str, Any], required: list[str] | None = None) -> JSONSchema:
    return {"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object", "properties": properties, "required": required or [], "additionalProperties": False}

MEMORY_SIGNAL_SCHEMA = object_schema({"event_type": {"type": "string", "default": "user_message"}, "text": {"type": "string", "minLength": 1, "maxLength": 20000}, "metadata": {"type": "object", "default": {}}, "session_id": {"type": ["string", "null"]}, "agent_id": {"type": ["string", "null"]}, "user_id": {"type": ["string", "null"]}}, ["text"])
MEMORY_QUERY_SCHEMA = object_schema({"query": {"type": "string", "minLength": 1, "maxLength": 2000}, "session_history": {"type": "array", "items": {"type": "string"}, "default": []}, "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 6}, "session_id": {"type": ["string", "null"]}, "agent_id": {"type": ["string", "null"]}, "user_id": {"type": ["string", "null"]}, "request_id": {"type": ["string", "null"]}}, ["query"])
MEMORY_COMMIT_SCHEMA = object_schema({"claim_id": {"type": "string", "minLength": 1}, "params": {"type": "object", "default": {}}}, ["claim_id"])
MEMORY_REVOKE_SCHEMA = object_schema({"claim_id": {"type": "string", "minLength": 1}, "reason": {"type": "string", "default": "mcp_revoke"}}, ["claim_id"])
MEMORY_DEBUG_SCHEMA = object_schema({"query": {"type": "string", "minLength": 1, "maxLength": 2000}, "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 10}}, ["query"])
MEMORY_STATS_SCHEMA = object_schema({}, [])
MEMORY_QUALITY_GATE_SCHEMA = object_schema({"goldens": {"type": "string", "default": "tests/fixtures/quality_goldens.jsonl"}, "min_quality_score": {"type": "number", "default": 0.50}, "max_failed_cases": {"type": "integer", "default": 3}}, [])
MEMORY_AUDIT_EXPORT_SCHEMA = object_schema({"output_path": {"type": "string", "default": "memoryx_audit_export.json"}, "redact": {"type": "boolean", "default": True}}, [])

MEMORYX_TOOL_SPECS = [
    ToolSpec(name="memory.signal", description="Ingest an interaction signal into MemoryX.", input_schema=MEMORY_SIGNAL_SCHEMA, read_only=False),
    ToolSpec(name="memory.query", description="Retrieve budgeted MemoryX context. Safe for default prompt injection.", input_schema=MEMORY_QUERY_SCHEMA, read_only=True),
    ToolSpec(name="memory.commit", description="Commit or inspect an existing claim by id.", input_schema=MEMORY_COMMIT_SCHEMA, read_only=False),
    ToolSpec(name="memory.revoke", description="Revoke a MemoryX claim by id.", input_schema=MEMORY_REVOKE_SCHEMA, read_only=False, destructive=True),
    ToolSpec(name="memory.debug", description="Return explicit retrieval debug. Not for default prompt injection.", input_schema=MEMORY_DEBUG_SCHEMA, read_only=True),
    ToolSpec(name="memory.stats", description="Return local MemoryX storage/runtime statistics.", input_schema=MEMORY_STATS_SCHEMA, read_only=True),
    ToolSpec(name="memory.quality_gate", description="Run the local MemoryX quality gate.", input_schema=MEMORY_QUALITY_GATE_SCHEMA, read_only=True),
    ToolSpec(name="memory.audit_export", description="Export a redacted audit bundle to local JSON.", input_schema=MEMORY_AUDIT_EXPORT_SCHEMA, read_only=True),
]