
from __future__ import annotations
from .adapter import MemoryXMCPAdapter
from .protocol import MCPToolRegistry
from .schemas import MEMORYX_TOOL_SPECS

def build_memoryx_tool_registry(db_path: str) -> MCPToolRegistry:
    adapter = MemoryXMCPAdapter(db_path)
    registry = MCPToolRegistry()
    handlers = {"memory.signal": adapter.signal, "memory.query": adapter.query, "memory.commit": adapter.commit,
                "memory.revoke": adapter.revoke, "memory.debug": adapter.debug, "memory.stats": adapter.stats,
                "memory.quality_gate": adapter.quality_gate, "memory.audit_export": adapter.audit_export}
    for spec in MEMORYX_TOOL_SPECS:
        registry.register(spec, handlers[spec.name])
    return registry
