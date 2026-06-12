# MemoryX

MemoryX is a long-term memory system for AI agents with hybrid retrieval, multi-layer storage, and cognitive decay models. It provides memory storage, retrieval, and management through a Python API, MCP server, and native Hermes Agent integration.

> **Latest: v3.1.0** — Configuration Wizard, install.sh integration, automatic env setup, sole-memory-source strategy. See [CHANGELOG](CHANGELOG.md).

## Features

- **Multi-layer memory**: working, short-term episodic, long-term semantic, consolidated knowledge, archive
- **Hybrid retrieval**: semantic vector + keyword (FTS5/BM25) + temporal + entity relationship + importance + episodic context
- **Cognitive models**: Ebbinghaus forgetting curve, Baddeley working memory, dual-process retrieval (System 1 / System 2), predictive coding, cognitive load optimization, procedural memory
- **Storage backend**: SQLite with FTS5 full-text search, optional vector database
- **Session isolation**: per-session scoping with global fallback
- **Conflict detection**: semantic and entity-level conflict detection
- **Memory lifecycle**: candidate -> committed -> verified -> superseded with version history
- **Evolutionary trajectory**: tracks how a user's preferences, opinions, and facts change over time per entity-slot (e.g. favorite singer 张杰 → 房东的猫) — kept as an append-only timeline rather than a conflict, with Ebbinghaus decay that down-weights but never deletes old nodes
- **MCP server**: Model Context Protocol support for external clients
- **Hermes Agent integration**: native provider, bridge, and tool interface

## Quick Start

### Option 1: Install from PyPI (minimal)
```bash
pip install memoryx
```

### Option 2: Clone and configure (recommended for full setup)
```bash
git clone https://github.com/luckyl214/memoryx.git
cd memoryx
bash configure_memoryx.sh
```

The configuration wizard will guide you through:
1. Checking your Python and SQLite environment
2. Choosing storage backend (SQLite or LanceDB vector hybrid)
3. Configuring LLM API (OpenAI, SiliconFlow, or custom) for memory extraction and cognitive reasoning
4. Configuring Embedding service (if vector storage is enabled)
5. Choosing integration mode (MCP Server, Hermes Agent, or Standalone API)
6. Setting the **memory source policy** — sole memory source or coexist with other memory systems
7. Toggling advanced modules (cognitive guard, temporal cognition, reflection, tool memory, meta-cognition, palace of memory, observability)
8. Automatically installing all dependencies and initializing the database
9. Providing ready-to-use launch commands

```bash
# Or use the legacy installer (creates venv and installs deps only, no interactive config):
bash install.sh
```

### Option 3: Manual setup
```bash
git clone https://github.com/luckyl214/memoryx.git
cd memoryx
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

### Verify
```bash
python -c "import memoryx; print('ok')"
pytest -q
```

## Memory Source Policy (v3.1.0+)

MemoryX supports two strategies for how it interacts with other memory systems (e.g., Hermes built-in memory, Claude projects, or other agent context stores):

### Sole Memory Source (`MEMORYX_UNIQUE_MEMORY_SOURCE=true`)

When enabled, MemoryX takes over **all** memory functions:
- External memory tools and context stores are suppressed
- Memory extraction runs on every turn
- MemoryX handles storage, retrieval, and context injection end-to-end
- No other memory mechanism should inject context into the agent

**Use this when** you want MemoryX to be the single source of truth for long-term memory and strict memory isolation.

### Coexistence Mode (default, `MEMORYX_UNIQUE_MEMORY_SOURCE=false`)

MemoryX works alongside other memory systems:
- MemoryX augments rather than replaces existing memory mechanisms
- Other memory tools and context stores remain active
- MemoryX extraction runs at the configured frequency
- The agent receives context from multiple sources

**Use this when** you want to layer MemoryX's cognitive memory features on top of an existing memory setup, or when evaluating MemoryX alongside your current system.

### Hermes Agent Coexistence

MemoryX integrates cleanly with Hermes Agent's built-in memory. In coexistence mode:

| Aspect | Behavior |
|--------|----------|
| Memory storage | MemoryX stores structured, scored, versioned memories via its provider; Hermes built-in memory continues to work independently |
| Context injection | MemoryX injects context through the `HermesBrdge`; (cognitive guard, narrative reflection, context blocks); Hermes may also inject its own context |
| Tool calls | MemoryX intercepts the `memory` tool call via `HermesCompatibilityAdapter`; other Hermes memory tools remain unaffected |
| Guard decisions | MemoryX's tool guard can block or allow memory operations based on safety and cognitive checks, without interfering with non-memory Hermes tools |
| Session lifecycle | MemoryX hooks into Hermes session events and works alongside existing session handlers |

There is no conflict — MemoryX operates at the memory-abstraction layer, while Hermes built-in memory operates at the platform level. They complement each other.

## Configuration Wizard Details

The `configure_memoryx.sh` script (v3.1.0+) is an interactive 5-step wizard:

| Step | What it does |
|------|-------------|
| **1/5** Check environment | Detects Python 3.11+, verifies SQLite FTS5 support |
| **2/5** Configure modules | Interactive prompts for storage, LLM, embedding, integration mode, memory source policy, and advanced modules |
| **3/5** Generate .env | Writes `MEMORYX_*` environment configuration, backs up existing `.env` |
| **4/5** Install dependencies | Creates `.venv`, installs core/optional deps, runs DB schema, verifies import |
| **5/5** Launch | Shows summary, offers to start MemoryX in the chosen mode, prints MCP config |

The wizard is designed to be run **once** after cloning. It is safe to re-run — it will back up any existing `.env` and skip already-created virtual environments.

## Installation Options

```bash
pip install memoryx              # Minimal
pip install memoryx[vector]      # With vector search (LanceDB + sentence-transformers)
pip install memoryx[mcp]         # With MCP server
pip install memoryx[dev]         # Development tools
```

Or install all extras:
```bash
pip install memoryx[vector,mcp,dev]
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

## MCP Server

```json
{
  "memoryx": {
    "command": "python",
    "args": ["-m", "memoryx.mcp.server"],
    "env": {
      "MEMORYX_ENV_FILE": "/path/to/memoryx/.env"
    }
  }
}
```

Compatible with Claude Code, Gemini CLI, and other MCP clients.

## Documentation

| Topic | Location |
|-------|----------|
| Configuration Wizard | Run `bash configure_memoryx.sh` |
| Hermes Integration | docs/HERMES_MEMORYX_AUTHORITATIVE.md |
| Cognitive Models | docs/cognitive/ |
| Pipeline (extraction / consolidation / storage / retrieval / forgetting) | docs/pipeline/ |
| Evolutionary trajectory / preference tracking | docs/evolution/ |
| Benchmarks & performance contracts | docs/benchmarks.md |
| Architecture overview | docs/architecture.md |
| API Reference | docs/ |
| Changelog | CHANGELOG.md |
| Credits | CREDITS.md |

## Requirements

- Python 3.11+
- SQLite 3.38+ (for FTS5 full-text search)
- Optional: sentence-transformers (for local vector search)
- Optional: LanceDB (for vector storage)
- Optional: MCP Python library (for MCP server)

## License

MIT License - see LICENSE for details.

## Contributing

See CONTRIBUTING.md for guidelines.
