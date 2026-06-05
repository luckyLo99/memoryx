# MCP Observability E2E

The MCP observability e2e suite has two layers.

## Always-on local registry e2e

This uses `build_memoryx_tool_registry()` and validates:

* `memory.signal`
* `memory.query`
* `memory.debug`
* `memory.stats`
* `memory.quality_gate`
* `memory.audit_export`
* TraceContext propagation
* retrieval event creation
* diagnostics artifacts

## Optional FastMCP e2e

This test is skipped unless the optional MCP SDK is installed.

```bash
pip install -r requirements-mcp.txt
pytest -q -m mcp_sdk
```

Skipped tests must include a clear reason:

```text
optional MCP SDK not installed; install requirements-mcp.txt to run FastMCP e2e
```
