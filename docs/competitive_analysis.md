# Competitive Analysis: MemoryX vs Mem0 / Letta / Zep

## Overview

| Feature | MemoryX | Mem0 | Letta | Zep |
|---------|---------|------|-------|-----|
| **Architecture** | Local-first, SQLite + optional vector | Cloud API + local SDK | Cloud API | Cloud API + self-hosted |
| **Open Source** | Yes (MIT) | Yes (Apache 2.0) | Yes (Apache 2.0) | Yes (MIT) |
| **Ebbinghaus Forgetting** | Built-in (customizable decay) | Built-in | Basic decay | Not native |
| **Working Memory** | Baddeley model (phonological loop + visuospatial sketchpad + episodic buffer) | Not provided | Not provided | Not provided |
| **Dual-Process Retrieval** | System 1 (fast) + System 2 (slow) | Single path | Single path | Single path |
| **Conflict Detection** | Built-in (semantic + entity-level) | Basic dedup | Not native | Not native |
| **Session Isolation** | per-session scoping + global fallback | Session support | Conversation-based | Session support |
| **Context Budget** | Token-aware injection with priority ranking | Not provided | Provided | Basic |
| **Cognitive Trust** | Source verification + evidence decay | Not provided | Not provided | Not provided |
| **Predictive Coding** | Active inference model | Not provided | Not provided | Not provided |
| **Procedural Memory** | Skill/pattern learning model | Not provided | Not provided | Not provided |
| **Memory Consolidation** | Background replay + reinforcement | Basic | Basic | Basic |
| **MCP Support** | Built-in MCP server | Not native | Not native | Not native |
| **Hermes Integration** | Native bridge + provider | N/A | N/A | N/A |
| **PII Filtering** | Built-in safety filter | Not provided | Not provided | Not provided |
| **Vector Search** | Optional (configurable) | Required | Required | Required |
| **Self-hosted** | Yes (no external deps) | No (cloud) | No (cloud) | Optional |
| **Offline mode** | Full offline | No | No | Limited |

## Feature Depth Comparison

### 1. Storage Architecture

- **MemoryX**: SQLite with JSON metadata, async I/O, versioned entries, quarantine state,
  candidate pipeline (uncommitted -> committed -> verified -> superseded).
  Full offline capability with zero external dependencies.
- **Mem0**: Cloud-first with vector embeddings. Local SDK caches but core logic is API-based.
  Requires network for write operations.
- **Letta**: Cloud API with conversation-based memory. No offline mode.
  Uses its own agent framework rather than pluggable memory.
- **Zep**: Cloud API with optional self-hosted Docker deployment.
  Graph-based memory relationships. Requires vector store.

### 2. Retrieval Quality

- **MemoryX**: Hybrid retrieval (BM25 keyword + vector + temporal + entity + intent scoring),
  dual-process (System 1 fast/intuitive vs System 2 slow/deliberate),
  multi-layer fusion with configurable weights.
- **Mem0**: Embedding similarity + recency. Good for simple QnA.
- **Letta**: Context window-based retrieval. Limited for long-term memory.
- **Zep**: Embedding + graph traversal. Good for relationship discovery.

### 3. Cognitive Science Foundation

- **MemoryX**: Ebbinghaus forgetting curve, Baddeley working memory model,
  dual-process theory (Kahneman), predictive coding / active inference (Friston),
  cognitive load theory (Sweller), procedural memory consolidation (Squire).
  These are grounded in published cognitive science and neuroscience papers.
- **Mem0**: Basic recency + frequency decay. Limited cognitive modeling.
- **Letta**: Conversation-based memory. No cognitive architecture.
- **Zep**: Graph-based with basic decay. Minimal cognitive science foundation.

### 4. Session and Multi-Tenant Support

- **MemoryX**: Per-session scoping with session_id, global vs session-only retrieval,
  cross-session conflict detection. Isolated session facts don't leak to global queries.
- **Mem0**: Session/user IDs supported through API.
- **Letta**: Conversation-based isolation only.
- **Zep**: User-level isolation. Session isolation via API.

### 5. Safety and Trust

- **MemoryX**: PII filter, evidence gate, cognitive trust scoring,
  candidate state machine (uncommitted -> verified), quarantine for low-trust memories,
  audit log for all mutations.
- **Others**: Basic content filtering at best. No trust pipeline.

## Quantitative Benchmark Targets

| Metric | MemoryX (local) | Mem0 (cloud) | Letta (cloud) | Zep (cloud) |
|--------|----------------|--------------|---------------|-------------|
| Write latency (10 facts) | < 200ms total | ~500ms+ (network) | ~800ms+ | ~400ms+ |
| Recall accuracy (10 facts) | > 90% | ~85% | ~80% | ~85% |
| Conflict detection rate | > 80% | Not provided | Not provided | Not provided |
| Session isolation | Native | API-based | Limited | API-based |
| Offline capable | Yes | No | No | Limited |
| Ebbinghaus decay | Built-in | Built-in | Basic | Not native |

*Note: Benchmark targets above are estimated. Run pytest tests/benchmarks/test_competitive_benchmark.py -v --tb=short
for actual MemoryX measurements. External system benchmarks require their respective API keys.*

## When to Choose Which System

| Use Case | Recommended | Rationale |
|----------|-------------|----------|
| Offline/local-first agent memory | **MemoryX** | Zero external deps, full offline |
| Hermes Agent integration | **MemoryX** | Native bridge and provider |
| Cognitive architecture research | **MemoryX** | Multiple cognitive models |
| Simple QnA with memory | Mem0 | Simpler API for basic use cases |
| Agent orchestration platform | Letta | Full agent framework |
| Graph-based memory exploration | Zep | Built-in knowledge graph |
| Multi-tenant SaaS memory | Mem0 / Zep | Managed cloud service |
| Research on forgetting curves | **MemoryX** | Ebbinghaus + spaced repetition |
| Working memory experiments | **MemoryX** | Baddeley model implementation |

## Summary

MemoryX distinguishes itself through:

1. **Cognitive depth** ? Multiple scientifically-grounded memory models
2. **Offline capability** ? Full functionality without network
3. **Hermes-native** ? Purpose-built for Hermes Agent integration
4. **Safety-first** ? PII filter, evidence gate, trust scoring pipeline
5. **Pluggable architecture** ? MCP server, configurable storage/retrieval

While Mem0/Letta/Zep are excellent for their target use cases,
MemoryX is the only system designed from the ground up as a
cognitive memory architecture for autonomous agents.
