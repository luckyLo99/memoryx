
from __future__ import annotations
from contextvars import ContextVar
from dataclasses import dataclass, asdict
from typing import Any

@dataclass(frozen=True)
class MCPRuntimeSession:
    session_id: str | None = None
    agent_id: str | None = None
    user_id: str | None = None
    run_id: str | None = None
    request_id: str | None = None
    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}

_session_var: ContextVar[MCPRuntimeSession] = ContextVar("memoryx_mcp_session", default=MCPRuntimeSession())

def bind_mcp_session(*, session_id=None, agent_id=None, user_id=None, run_id=None, request_id=None):
    from memoryx.observability.context import bind_observability_context
    session = MCPRuntimeSession(session_id=session_id, agent_id=agent_id, user_id=user_id, run_id=run_id, request_id=request_id)
    token = _session_var.set(session)
    trace_token = bind_observability_context(session_id=session_id)
    return token, trace_token

def current_mcp_session() -> MCPRuntimeSession:
    return _session_var.get()
