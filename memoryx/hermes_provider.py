"""MemoryX Hermes Memory Provider — native memory tool replacement layer.

Replaces Hermes' built-in MEMORY.md / USER.md with MemoryX-backed
memory tool operations. All writes go through MemoryCandidateService
to ensure evidence-gated candidate pipeline compliance.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from memoryx.hermes_bridge import HermesMemoryBridge
from memoryx.services.memory_candidate_service import (
    CandidateDecision,
    CandidateState,
    EvidenceLevel,
    MemoryCandidatePolicy,
    MemoryCandidateRequest,
    MemoryCandidateService,
)

logger = logging.getLogger(__name__)

_VALID_ACTIONS = frozenset({"add", "read", "list", "replace", "remove", "usage", "export"})
_VALID_TARGETS = frozenset({"memory", "user", "project", "policy"})
_DEFAULT_LIMIT = 20
_MAX_LIMIT = 100

# Target -> (memory_type, scope) mapping
_TARGET_MAP: dict[str, tuple[str, str]] = {
    "memory": ("FACT", "global"),
    "user": ("PREFERENCE", "user"),
    "project": ("PROJECT", "project"),
    "policy": ("FACT", "global"),  # policy uses memory_class=policy in metadata
}


def _clamp_limit(limit: int) -> int:
    return min(max(1, limit), _MAX_LIMIT)


def _safe_metadata_value(val: Any) -> Any:
    """Ensure metadata values are JSON-serializable."""
    if isinstance(val, (str, int, float, bool)):
        return val
    if val is None:
        return None
    return str(val)


def _build_tool_schema() -> list[dict[str, Any]]:
    return [
        {
            "name": "memory",
            "description": (
                "Persistent memory tool backed by MemoryX. Stores, retrieves, "
                "and manages long-term memories across sessions. "
                "Actions: add (create candidate), read (view by id/query), "
                "list (summarize), replace (propose replacement), "
                "remove (propose deletion), usage (usage statistics)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": list(_VALID_ACTIONS),
                        "description": "Operation to perform.",
                    },
                    "target": {
                        "type": "string",
                        "enum": list(_VALID_TARGETS),
                        "description": (
                            "Memory category. memory=FACT (global), "
                            "user=user preferences, project=project state, "
                            "policy=rules/policies."
                        ),
                    },
                    "content": {
                        "type": "string",
                        "description": "Content for add/replace operations.",
                    },
                    "memory_id": {
                        "type": "string",
                        "description": "Memory ID for read/replace/remove operations.",
                    },
                    "query": {
                        "type": "string",
                        "description": "Search query for read/list operations.",
                    },
                    "include_candidates": {
                        "type": "boolean",
                        "description": "Include candidate/verified memories in results.",
                        "default": False,
                    },
                    "format": {
                        "type": "string",
                        "enum": ["memory_md", "user_md", "markdown", "json"],
                        "description": "Output format for export action: memory_md (MEMORY.md style), user_md (USER.md style), markdown, json.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results (default 20, max 100).",
                        "default": _DEFAULT_LIMIT,
                    },
                    "reason": {
                        "type": "string",
                        "description": "Reason for replace/remove operations.",
                    },
                    "evidence_level": {
                        "type": "string",
                        "enum": [e.value for e in EvidenceLevel],
                        "description": "Evidence level for add operations.",
                        "default": EvidenceLevel.E0_MODEL_INFERENCE.value,
                    },
                    "source_event_id": {
                        "type": "string",
                        "description": "Source event identifier for provenance.",
                    },
                    "confidence": {
                        "type": "number",
                        "description": "Confidence score (0.0-1.0). Default 0.0 (E0).",
                        "default": 0.0,
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Tags for the memory entry.",
                    },
                    "entities": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Named entities referenced in the memory.",
                    },
                },
                "required": ["action"],
            },
        }
    ]


class MemoryXHermesProvider:
    """Hermes native memory tool replacement backed by MemoryX.

    Provides memory(action=...) tool with full candidate pipeline integration.
    All writes create candidates, never committed directly.
    """

    name = "memoryx"

    def __init__(self, *, bridge: HermesMemoryBridge) -> None:
        self.bridge = bridge
        self._candidate_service: MemoryCandidateService | None = None

    @property
    def candidate_service(self) -> MemoryCandidateService:
        if self._candidate_service is None:
            self._candidate_service = MemoryCandidateService(
                repository=self.bridge.repository,
                policy=MemoryCandidatePolicy(),
            )
        return self._candidate_service

    def get_tool_schemas(self) -> list[dict[str, Any]]:
        """Return the unified memory tool schema."""
        return _build_tool_schema()

    async def handle_tool_call(
        self, tool_name: str, arguments: dict[str, Any], session_id: str | None = None,
    ) -> dict[str, Any]:
        """Handle a memory tool call. Routes to the correct action handler."""
        if tool_name != "memory":
            return {"ok": False, "error": f"unsupported tool: {tool_name}"}

        action = arguments.get("action", "").strip().lower()
        if action not in _VALID_ACTIONS:
            return {"ok": False, "error": f"invalid action '{action}'. Valid: {', '.join(sorted(_VALID_ACTIONS))}"}

        handler = getattr(self, f"_handle_{action}", None)
        if handler is None:
            return {"ok": False, "error": f"action '{action}' not implemented"}

        try:
            result = await handler(arguments, session_id=session_id or "")
            return result
        except Exception as e:
            logger.exception("memory tool error: action=%s", action)
            return {"ok": False, "error": f"internal error: {e}"}

    # ------------------------------------------------------------------
    # action=add
    # ------------------------------------------------------------------

    async def _handle_add(self, args: dict[str, Any], session_id: str) -> dict[str, Any]:
        target = args.get("target", "memory").strip().lower()
        content = args.get("content", "").strip()
        evidence_level = args.get("evidence_level", EvidenceLevel.E0_MODEL_INFERENCE.value)
        source_event_id = args.get("source_event_id")
        confidence = float(args.get("confidence", 0.0))
        tags = args.get("tags", [])
        entities = args.get("entities", [])

        # Validate target
        if target not in _VALID_TARGETS:
            return {"ok": False, "error": f"invalid target '{target}'. Valid: {', '.join(sorted(_VALID_TARGETS))}"}

        # Empty content
        if not content:
            return {"ok": False, "error": "content cannot be empty"}

        # Map target to memory_type/scope
        memory_type, scope = _TARGET_MAP[target]

        # Build metadata
        metadata: dict[str, Any] = {
            "native_tool_action": "add",
            "native_target": target,
            "committed_by_tool": False,
        }
        if target == "policy":
            metadata["memory_class"] = "policy"

        request = MemoryCandidateRequest(
            content=content,
            session_id=session_id or None,
            memory_type=memory_type,
            scope=scope,
            source_type="hermes_memory_tool",
            source_event_id=source_event_id or None,
            evidence_ids=[],
            evidence_level=evidence_level,
            confidence=confidence,
            metadata=metadata,
            tags=list(tags) if isinstance(tags, list) else [],
            entities=list(entities) if isinstance(entities, list) else [],
        )

        try:
            memory_id = await self.candidate_service.create_candidate(request)
        except ValueError as e:
            return {"ok": False, "error": str(e)}

        state = await self.candidate_service.get_candidate_state(memory_id) or CandidateState.CANDIDATE.value

        return {
            "ok": True,
            "action": "add",
            "state": state,
            "memory_id": memory_id,
            "message": "已创建候选记忆，等待验证后提交",
        }

    # ------------------------------------------------------------------
    # action=read
    # ------------------------------------------------------------------

    async def _handle_read(self, args: dict[str, Any], session_id: str) -> dict[str, Any]:
        memory_id = args.get("memory_id", "").strip()
        query = args.get("query", "").strip()
        include_candidates = bool(args.get("include_candidates", False))
        limit = _clamp_limit(args.get("limit", _DEFAULT_LIMIT))

        repo = self.bridge.repository

        if memory_id:
            mem = await repo.get_memory(memory_id)
            if mem is None:
                return {"ok": False, "error": f"memory not found: {memory_id}"}
            result = self._summarize_memory(mem, include_candidates=include_candidates)
            if result is None:
                return {"ok": False, "error": "memory is not available"}
            return {"ok": True, "action": "read", "memories": [result]}

        if query:
            raw = await repo.search_memories_text(query, limit=limit)
        else:
            states = {"active", "archived"}
            if include_candidates:
                states = {"active", "archived", "superseded", "quarantined"}
            raw = await repo.list_memories_filtered(limit=limit, include_states=states)

        results = []
        for m in raw:
            r = self._summarize_memory(m, include_candidates=include_candidates)
            if r is not None:
                results.append(r)

        return {
            "ok": True,
            "action": "read",
            "count": len(results),
            "memories": results,
        }

    # ------------------------------------------------------------------
    # action=list
    # ------------------------------------------------------------------

    async def _handle_list(self, args: dict[str, Any], session_id: str) -> dict[str, Any]:
        target = args.get("target", "").strip().lower()
        include_candidates = bool(args.get("include_candidates", False))
        limit = _clamp_limit(args.get("limit", _DEFAULT_LIMIT))

        repo = self.bridge.repository

        states = {"active", "archived"}
        if include_candidates:
            states = {"active", "archived", "superseded", "quarantined"}

        if target and target in _TARGET_MAP:
            memory_type, scope = _TARGET_MAP[target]
            raw = await repo.list_memories_filtered(
                limit=limit, memory_type=memory_type, scope=scope, include_states=states,
            )
        else:
            raw = await repo.list_memories_filtered(limit=limit, include_states=states)

        results = []
        for m in raw:
            r = self._summarize_memory(m, include_candidates=True)
            if r is not None:
                results.append(r)

        return {
            "ok": True,
            "action": "list",
            "count": len(results),
            "memories": results,
        }

    # ------------------------------------------------------------------
    # action=replace
    # ------------------------------------------------------------------

    async def _handle_replace(self, args: dict[str, Any], session_id: str) -> dict[str, Any]:
        memory_id = args.get("memory_id", "").strip()
        content = args.get("content", "").strip()
        reason = args.get("reason", "replacement requested")

        if not memory_id:
            return {"ok": False, "error": "memory_id is required"}
        if not content:
            return {"ok": False, "error": "content cannot be empty"}

        repo = self.bridge.repository
        target_mem = await repo.get_memory(memory_id)
        if target_mem is None:
            return {"ok": False, "error": f"target memory not found: {memory_id}"}

        # Create replacement candidate
        tgt_meta = self._parse_metadata(target_mem.get("metadata_json", "{}"))
        metadata: dict[str, Any] = {
            "native_tool_action": "replace",
            "replace_target_id": memory_id,
            "replacement_reason": reason,
            "candidate_state": CandidateState.CANDIDATE.value,
            "committed_by_tool": False,
        }

        request = MemoryCandidateRequest(
            content=content,
            session_id=session_id or None,
            memory_type=target_mem.get("memory_type", "FACT"),
            scope=target_mem.get("scope", "global"),
            source_type="hermes_memory_tool",
            source_event_id=tgt_meta.get("source_event_id"),
            evidence_ids=[],
            evidence_level=EvidenceLevel.E0_MODEL_INFERENCE.value,
            confidence=0.0,
            metadata=metadata,
            tags=tgt_meta.get("tags", []),
            entities=tgt_meta.get("entities", []),
        )

        try:
            replacement_id = await self.candidate_service.create_candidate(request)
        except ValueError as e:
            return {"ok": False, "error": str(e)}

        return {
            "ok": True,
            "action": "replace",
            "state": CandidateState.CANDIDATE.value,
            "memory_id": replacement_id,
            "replace_target_id": memory_id,
            "message": "Replacement candidate created. Verify then commit to supersede original.",
        }

    # ------------------------------------------------------------------
    # action=remove
    # ------------------------------------------------------------------

    async def _handle_remove(self, args: dict[str, Any], session_id: str) -> dict[str, Any]:
        memory_id = args.get("memory_id", "").strip()
        reason = args.get("reason", "removal requested")

        if not memory_id:
            return {"ok": False, "error": "memory_id is required"}

        repo = self.bridge.repository
        mem = await repo.get_memory(memory_id)
        if mem is None:
            return {"ok": False, "error": f"memory not found: {memory_id}"}

        cs = self.candidate_service

        # If target is a candidate (not committed), reject it
        meta = self._parse_metadata(mem.get("metadata_json", "{}"))
        candidate_state = meta.get("candidate_state", "missing")
        active_state = mem.get("active_state", "")

        if candidate_state in (CandidateState.CANDIDATE.value, CandidateState.VERIFIED.value):
            ok = await cs.reject_candidate(memory_id, reason)
            if ok:
                return {
                    "ok": True,
                    "action": "remove",
                    "state": CandidateState.REJECTED.value,
                    "target_memory_id": memory_id,
                    "message": "Candidate rejected.",
                }
            return {"ok": False, "error": "failed to reject candidate"}

        if candidate_state == CandidateState.COMMITTED.value or active_state in ("active", "archived"):
            # Create deletion candidate
            metadata: dict[str, Any] = {
                "native_tool_action": "remove",
                "remove_target_id": memory_id,
                "removal_reason": reason,
            }
            request = MemoryCandidateRequest(
                content=f"Request to remove memory {memory_id}",
                session_id=session_id or None,
                memory_type="FACT",
                scope="global",
                source_type="hermes_memory_tool",
                source_event_id=meta.get("source_event_id"),
                evidence_ids=[],
                evidence_level=EvidenceLevel.E0_MODEL_INFERENCE.value,
                confidence=0.0,
                metadata=metadata,
            )
            try:
                removal_id = await cs.create_candidate(request)
            except ValueError as e:
                return {"ok": False, "error": str(e)}

            return {
                "ok": True,
                "action": "remove",
                "state": CandidateState.CANDIDATE.value,
                "target_memory_id": memory_id,
                "deletion_candidate_id": removal_id,
                "message": "Deletion candidate created. Verify before removal takes effect.",
            }

        return {
            "ok": True,
            "action": "remove",
            "state": candidate_state,
            "target_memory_id": memory_id,
            "message": f"Memory is in state '{candidate_state}'. No action taken.",
        }

    # ------------------------------------------------------------------
    # action=usage
    # ------------------------------------------------------------------

    async def _handle_usage(self, args: dict[str, Any], session_id: str) -> dict[str, Any]:
        repo = self.bridge.repository
        by_state = await repo.count_memories_by_state()
        by_type_scope = await repo.count_memories_by_type_scope()

        total = sum(by_state.values())
        committed = by_state.get("active", 0)
        archived = by_state.get("archived", 0)
        superseded = by_state.get("superseded", 0)
        quarantined = by_state.get("quarantined", 0)

        # Count candidate states from metadata
        candidate_count = 0
        verified_count = 0
        rejected_count = 0
        cand_rows = await repo.list_memories_filtered(limit=_MAX_LIMIT * 10)
        for r in cand_rows:
            m = self._parse_metadata(r.get("metadata_json", "{}"))
            cs = m.get("candidate_state", "")
            if cs == CandidateState.CANDIDATE.value:
                candidate_count += 1
            elif cs == CandidateState.VERIFIED.value:
                verified_count += 1
            elif cs == CandidateState.REJECTED.value:
                rejected_count += 1

        # Rough char estimate from content length
        total_chars = 0
        all_rows = await repo.list_memories_filtered(limit=1000)
        for r in all_rows:
            total_chars += len(str(r.get("content", "")))

        by_type: dict[str, int] = {}
        for mt, scopes in by_type_scope.items():
            by_type[mt] = sum(scopes.values())

        return {
            "ok": True,
            "action": "usage",
            "total_memories": total,
            "committed_count": committed,
            "active_count": committed,
            "archived_count": archived,
            "superseded_count": superseded,
            "quarantined_count": quarantined,
            "candidate_count": candidate_count,
            "verified_count": verified_count,
            "rejected_count": rejected_count,
            "by_memory_type": by_type,
            "by_scope": {sc: {"total": total} for sc in set(s for t in by_type_scope.values() for s in t)},
            "approximate_content_chars": total_chars,
            "limit_note": "Character count is approximate. DB path and secrets are not exposed.",
        }

    # ------------------------------------------------------------------
    # action=export
    # ------------------------------------------------------------------

    async def _handle_export(self, args: dict[str, Any], session_id: str) -> dict[str, Any]:
        """Export memories in human-readable format."""
        fmt = args.get("format", "markdown").strip().lower()
        target = args.get("target", "").strip().lower()
        include_candidates = bool(args.get("include_candidates", False))
        limit = _clamp_limit(args.get("limit", _DEFAULT_LIMIT))

        valid_formats = {"memory_md", "user_md", "markdown", "json"}
        if fmt not in valid_formats:
            return {"ok": False, "error": f"invalid format '{fmt}'. Valid: {', '.join(sorted(valid_formats))}"}

        repo = self.bridge.repository
        states = {"active", "archived"} if not include_candidates else {"active", "archived", "superseded", "quarantined"}

        # Fetch memories
        if target and target in _TARGET_MAP:
            memory_type, scope = _TARGET_MAP[target]
            raw = await repo.list_memories_filtered(
                limit=limit, memory_type=memory_type, scope=scope, include_states=states,
            )
        elif target == "policy":
            raw = await repo.list_memories_filtered(limit=limit, include_states=states)
            # Filter for policy via metadata
        else:
            raw = await repo.list_memories_filtered(limit=limit, include_states=states)

        # Summarize, filtering per rules
        summaries = []
        for m in raw:
            s = self._summarize_memory(m, include_candidates=include_candidates)
            if s is not None:
                summaries.append(s)

        # Filter for policy target (needs metadata check)
        if target == "policy":
            summaries = [s for s in summaries if s.get("memory_class") == "policy"]

        if fmt == "json":
            return {"ok": True, "action": "export", "format": "json", "count": len(summaries), "memories": summaries}

        # Build markdown
        lines: list[str] = []
        if fmt == "memory_md":
            lines.append("# MemoryX MEMORY Export")
            lines.append("")
        elif fmt == "user_md":
            lines.append("# MemoryX USER Export")
            lines.append("")
        else:
            lines.append("# MemoryX Memory Export")
            lines.append("")

        # Group by type
        sections: dict[str, list[str]] = {
            "Project State": [],
            "User Preferences": [],
            "Facts": [],
            "Policies / Lessons": [],
            "Candidates": [],
        }

        for s in summaries:
            prefix = ""
            cs = s.get("candidate_state", "")
            if cs == CandidateState.CANDIDATE.value or cs == CandidateState.VERIFIED.value:
                prefix = f"[{cs.upper()}] "
            elif cs == CandidateState.COMMITTED.value:
                prefix = "[COMMITTED] "

            entry = f"{prefix}{s.get('content', '')}"
            if s.get("memory_type") == "PREFERENCE":
                sections["User Preferences"].append(entry)
            elif s.get("memory_type") == "PROJECT":
                sections["Project State"].append(entry)
            elif s.get("native_tool_action") == "add" and s.get("native_target") == "policy":
                sections["Policies / Lessons"].append(entry)
            elif cs in (CandidateState.CANDIDATE.value, CandidateState.VERIFIED.value):
                sections["Candidates"].append(entry)
            else:
                sections["Facts"].append(entry)

        for title, entries in sections.items():
            if not entries:
                continue
            # For user_md format, only show user-related sections
            if fmt == "user_md" and title not in ("User Preferences", "Facts", "Candidates"):
                continue
            # For memory_md format, only show non-user sections
            if fmt == "memory_md" and title == "User Preferences":
                continue
            lines.append(f"## {title}")
            for e in entries:
                lines.append(f"§ {e}")
            lines.append("")

        if lines[-1] == "":
            lines.pop()

        return {"ok": True, "action": "export", "format": fmt, "text": "\\n".join(lines), "count": len(summaries)}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _summarize_memory(
        self, mem: dict[str, Any], include_candidates: bool = False,
    ) -> dict[str, Any] | None:
        """Return a safe summary dict for a memory record.

        Returns None if the memory should be hidden (e.g. rejected/superseded
        and include_candidates is False).
        """
        active_state = mem.get("active_state", "")
        metadata = self._parse_metadata(mem.get("metadata_json", "{}"))
        candidate_state = metadata.get("candidate_state", "")

        # Default: hide rejected/superseded
        if not include_candidates:
            if candidate_state in (CandidateState.REJECTED.value, CandidateState.SUPERSEDED.value):
                return None
            if active_state == "superseded":
                return None
            if active_state == "quarantined" and candidate_state != CandidateState.CANDIDATE.value:
                return None
        else:
            if candidate_state == CandidateState.REJECTED.value:
                return None  # always hide rejected

        # Build safe summary
        result: dict[str, Any] = {
            "memory_id": mem.get("id", mem.get("memory_id", "")),
            "content": str(mem.get("content", ""))[:500],
            "memory_type": mem.get("memory_type", ""),
            "scope": mem.get("scope", ""),
            "active_state": active_state,
            "candidate_state": candidate_state or None,
            "evidence_level": metadata.get("evidence_level"),
            "confidence": metadata.get("confidence"),
            "source_event_id": metadata.get("source_event_id"),
            "tags": metadata.get("tags", mem.get("tags_json", "[]")),
            "entities": metadata.get("entities", mem.get("entities_json", "[]")),
            "native_target": metadata.get("native_target"),
            "native_tool_action": metadata.get("native_tool_action"),
            "created_at": mem.get("created_at", ""),
            "updated_at": mem.get("updated_at", ""),
        }
        # Parse tags/entities if they're JSON strings
        for field in ("tags", "entities"):
            val = result.get(field)
            if isinstance(val, str):
                try:
                    result[field] = json.loads(val)
                except (json.JSONDecodeError, ValueError):
                    result[field] = [val]

        return result

    @staticmethod
    def _parse_metadata(metadata_json: str) -> dict[str, Any]:
        try:
            return json.loads(metadata_json) if metadata_json else {}
        except (json.JSONDecodeError, ValueError):
            return {}
