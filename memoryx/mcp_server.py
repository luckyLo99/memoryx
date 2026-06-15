"""DEPRECATED — moved to memoryx.mcp.server."""
from __future__ import annotations
import warnings as _w
_w.warn("memoryx.mcp_server is deprecated; use memoryx.mcp.server", DeprecationWarning, stacklevel=2)
from memoryx.mcp.server import MCPServer  # noqa: E402
__all__ = ["MCPServer"]
