# MemoryX

MemoryX is a long-term memory system for AI agents with hybrid retrieval, multi-layer storage, and cognitive decay models. It provides memory storage, retrieval, and management through a Python API, MCP server, and native Hermes Agent integration.

## Features

- **Multi-layer memory**: working, short-term episodic, long-term semantic, consolidated knowledge, archive
- **Hybrid retrieval**: semantic vector + keyword (FTS5/BM25) + temporal + entity relationship + importance + episodic context
- **Cognitive models**: Ebbinghaus forgetting curve, Baddeley working memory, dual-process retrieval (System 1 / System 2), predictive coding, cognitive load optimization, procedural memory
- **Storage backend**: SQLite with FTS5 full-text search, optional vector database
- **Session isolation**: per-session scoping with global fallback
- **Conflict detection**: semantic and entity-level conflict detection
- **Memory lifecycle**: candidate -> committed -> verified -> superseded with version history
- **MCP server**: Model Context Protocol support for external clients
- **Hermes Agent integration**: native provider, bridge, and tool interface

## Quick Start

```bash
pip install memoryx
# Or from source:
git clone https://github.com/luckyl214/memoryx.git
cd memoryx
pip install -e .
```

Run self-check:

```bash
memoryx doctor
```

Run tests:

```bash
pytest -q
```

## Hermes Agent Usage

```python
from memoryx.hermes.provider import MemoryXHermesProvider
from memoryx.hermes.bridge import HermesMemoryBridge
from memoryx.storage.repository import MemoryRepository

repo = MemoryRepository("./memory.db")
await repo.open()
provider = MemoryXHermesProvider(
    bridge=HermesMemoryBridge(repository=repo)
)

# Store a memory
result = await provider.handle_tool_call("memory", {
    "action": "add",
    "content": "User prefers Python for data analysis"
})

# Retrieve memories
result = await provider.handle_tool_call("memory", {
    "action": "read",
    "query": "Python"
})
```

## Installation Options

```bash
pip install memoryx              # Minimal
pip install memoryx[vector]      # With vector search
pip install memoryx[mcp]         # With MCP server
pip install memoryx[dev]         # Development tools
```

## Architecture

```
User Input -> Hermes Agent
                |
    MemoryXHermesProvider -> HermesMemoryBridge
                                |
                     MemoryCandidateService
                                |
    +---------------------------+---------------------------+
    |                       Storage                          |
    |   MemoryRepository (SQLite FTS5 + optional Vector DB)  |
    +--------------------------------------------------------+
    |                     Retrieval                           |
    |   HybridRetrievalEngine (6-channel scoring + decay)    |
    +--------------------------------------------------------+
    |                  Cognitive Modules                      |
    |   Ebbinghaus | Baddeley | Dual-Process | Predictive    |
    +--------------------------------------------------------+
    |                   Context Injection                     |
    +--------------------------------------------------------+
                                |
                        Agent Response
```

## Documentation

| Topic | Location |
|-------|----------|
| Hermes Integration | docs/HERMES_MEMORYX_AUTHORITATIVE.md |
| Cognitive Models | docs/cognitive/ |
| API Reference | docs/ |
| Changelog | CHANGELOG.md |
| Credits | CREDITS.md |

## Requirements

- Python 3.11+
- SQLite 3.38+ (for FTS5)
- Optional: sentence-transformers (for vector search)

## License

MIT License - see LICENSE for details.

## Contributing

See CONTRIBUTING.md for guidelines.
