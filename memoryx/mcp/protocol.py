
from __future__ import annotations
from typing import Any, Callable
from .schemas import ToolCallResult, ToolSpec

class ToolValidationError(ValueError): pass

class MCPToolRegistry:
    def __init__(self):
        self.specs: dict[str, ToolSpec] = {}
        self.handlers: dict[str, Callable[[dict[str, Any]], Any]] = {}
    def register(self, spec: ToolSpec, handler):
        if spec.name in self.specs: raise ValueError(f"duplicate tool: {spec.name}")
        self.specs[spec.name] = spec; self.handlers[spec.name] = handler
    def list_tools(self) -> list[dict[str, Any]]:
        return [{"name": s.name, "description": s.description, "inputSchema": s.input_schema,
                 "annotations": {"readOnlyHint": s.read_only, "destructiveHint": s.destructive}}
                for s in self.specs.values()]
    def call(self, name: str, arguments: dict[str, Any] | None = None) -> ToolCallResult:
        if name not in self.specs: return ToolCallResult(ok=False, error=f"unknown tool: {name}", tool_name=name)
        args = arguments or {}
        try: result = self.handlers[name](args); return ToolCallResult(ok=True, data=result, tool_name=name)
        except Exception as exc: return ToolCallResult(ok=False, error=str(exc), tool_name=name)
