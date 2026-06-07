"""MCP server - exposes MemoryX as MCP native tools.
Compatible with Claude Code, Gemini CLI, and other MCP clients.
"""

from __future__ import annotations

from typing import Any


class MCPServer:
    """Lightweight MCP server exposing memoryx tools."""

    def __init__(
        self,
        api,
        embedding_manager=None,
        *,
        allow_embedding_fallback: bool = False,
        candidate_service=None,
    ) -> None:
        self.api = api
        self.embedding_manager = embedding_manager
        self.allow_embedding_fallback = allow_embedding_fallback
        self._candidate_service = candidate_service
        self._tools: dict[str, dict] = {}

        # instrument MCP tools for observability
        try:
            from memoryx.mcp.observed import instrument_mcp_server
            instrument_mcp_server(
                self,
                tool_names=["memoryx_search", "memoryx_feedback"],
            )
        except ImportError:
            pass

    async def _query_vector(self, query: str) -> list[float]:
        if self.embedding_manager is not None:
            try:
                return await self.embedding_manager.embed_text(query)
            except Exception:
                pass
        return []

    def list_tools(self) -> list[dict]:
        return [
            {
                "name": "memoryx_search",
                "description": "Search structured long-term memory",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "limit": {"type": "integer", "default": 5},
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "memoryx_conversation_search",
                "description": "Search raw conversation history",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "session_id": {"type": "string"},
                        "limit": {"type": "integer", "default": 5},
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "memoryx_reflect",
                "description": "Cross-memory LLM synthesis reasoning",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "limit": {"type": "integer", "default": 10},
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "memoryx_feedback",
                "description": "Provide feedback for a memory",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "memory_id": {"type": "string"},
                        "positive": {"type": "boolean"},
                    },
                    "required": ["memory_id", "positive"],
                },
            },
            {
                "name": "memoryx_store",
                "description": "Store a memory",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "content": {"type": "string"},
                        "memory_type": {"type": "string", "default": "FACT"},
                        "scope": {"type": "string", "default": "global"},
                    },
                    "required": ["content"],
                },
            },
        ]

    async def handle_call(self, tool_name: str, arguments: dict) -> Any:
        if tool_name == "memoryx_search":
            query = arguments["query"]
            query_vector = await self._query_vector(query)
            return await self.api.search(
                query=query,
                query_vector=query_vector,
                limit=arguments.get("limit", 5),
                tag_filter=arguments.get("tag_filter"),
            )
        elif tool_name == "memoryx_conversation_search":
            return await self.api.conversation_search(
                query=arguments["query"],
                session_id=arguments.get("session_id"),
                limit=arguments.get("limit", 5),
            )
        elif tool_name == "memoryx_reflect":
            query = arguments["query"]
            query_vector = await self._query_vector(query)
            return await self.api.reflect_synthesis(
                query=query,
                query_vector=query_vector,
                limit=arguments.get("limit", 10),
            )
        elif tool_name == "memoryx_feedback":
            return await self.api.feedback(
                memory_id=arguments["memory_id"],
                positive=arguments["positive"],
            )
        elif tool_name == "memoryx_store":
            cs = getattr(self, "_candidate_service", None)
            if cs is not None:
                from memoryx.services.memory_candidate_service import (
                    CandidateDecision,
                    EvidenceLevel,
                    MemoryCandidateRequest,
                )
                req = MemoryCandidateRequest(
                    content=arguments["content"],
                    memory_type=arguments.get("memory_type", "FACT"),
                    scope=arguments.get("scope", "global"),
                    source_event_id="mcp_memoryx_store",
                    evidence_level=EvidenceLevel.E3_TOOL_OR_TEST_SUPPORTED,
                    decision=CandidateDecision.AUTO_PROMOTE,
                )
                result = await cs.submit_candidate(req)
                return {"memory_id": result.memory_id} if result else {"error": "candidate submission failed"}
            return {
                "memory_id": await self.api.store(
                    content=arguments["content"],
                    memory_type=arguments.get("memory_type", "FACT"),
                    scope=arguments.get("scope", "global"),
                )
            }
        return {"error": f"Unknown tool: {tool_name}"}
