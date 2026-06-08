# Credits and Acknowledgments

**MemoryX v3.0.0** is not built from scratch. It stands on the shoulders of giants, drawing inspiration and design patterns from numerous open-source projects, academic research papers, and cognitive science theories.

---

## Open-Source Projects

### Direct Architectural Inspiration

| Project | Repository | Inspiration |
|---------|-----------|-------------|
| **Hermes Agent** | [github.com/NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent) | Plugin architecture, MemoryProvider abstraction, Hook system, tool-calling lifecycle |
| **MemPalace** | [github.com/MemPalace/mempalace](https://github.com/MemPalace/mempalace) | Wing->Room->Drawer hierarchical navigation, AAAK symbolic indexing, MCP native interface |
| **Hindsight** | [github.com/vectorize-io/hindsight](https://github.com/vectorize-io/hindsight) | Cross-memory LLM synthesis (hindsight_reflect), memory bank, tag system, multi-strategy retrieval |
| **Mem0** | [github.com/mem0ai/mem0](https://github.com/mem0ai/mem0) | Multi-category organization (user/session/agent), Profile management |
| **TencentDB Agent Memory** | [github.com/TencentDB/Agent-Memory](https://github.com/TencentDB/Agent-Memory) | L0->L3 semantic pyramid, Progressive Disclosure, Persona synthesis, Scene blocks |
| **Letta (MemGPT)** | [github.com/letta-ai/letta](https://github.com/letta-ai/letta) | Hierarchical memory, context budget auto-pagination, self-edit interface |
| **Zep** | [github.com/getzep/zep](https://github.com/getzep/zep) | Temporal knowledge graph, entity disambiguation, conversation summarization |
| **Cognee** | [github.com/topoteretes/cognee](https://github.com/topoteretes/cognee) | Knowledge distillation, ECL pipeline for hierarchical memory |
| **Holographic Memory** | Hermes Agent built-in plugin | Trust scoring, zero-dependency, SQLite FTS5 minimal design |
| **GBrain** | — | Local-first design philosophy |

### Development Tools and Infrastructure

- **Python** — The Python Software Foundation for the language and ecosystem
- **SQLite** — D. Richard Hipp for the embedded database engine
- **pytest** — The pytest team for the testing framework
- **FastAPI** — Sebastián Ramírez for the async web framework
- **Pydantic** — Samuel Colvin for data validation
- **structlog** — Hynek Schlawack for structured logging
- **prometheus-client** — The Prometheus team for monitoring

---

## Academic Research Papers

### Cognitive Science Foundations

| Paper | Authors | Application in MemoryX |
|-------|---------|----------------------|
| **"Memory: A Contribution to Experimental Psychology"** (1885/1913) | Hermann Ebbinghaus | Ebbinghaus forgetting curve implementation (`cognitive/ebbinghaus.py`) |
| **"Working Memory"** (1992) | Alan Baddeley | Baddeley multi-component working memory model (`cognitive/working_memory.py`) |
| **"Thinking, Fast and Slow"** (2011) | Daniel Kahneman | Dual-process theory for System 1 / System 2 retrieval (`cognitive/dual_process.py`) |
| **"The free-energy principle: a unified brain theory"** (2010) | Karl Friston | Predictive coding and active inference (`cognitive/predictive_coding.py`) |
| **"Cognitive Load During Problem Solving: Effects on Learning"** (1988) | John Sweller | Cognitive load theory and optimization (`cognitive/cognitive_load.py`) |
| **"Memory and the hippocampal complex"** (1986) | Larry Squire, Stuart Zola-Morgan | Memory consolidation and replay (`consolidation/replay.py`) |

### Memory Systems in AI

| Paper | Relevance |
|-------|-----------|
| **"Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks"** (Lewis et al., 2020) | RAG pattern for memory retrieval |
| **"MemGPT: Towards LLMs as Operating Systems"** (Packer et al., 2023) | Context budget management, hierarchical memory |
| **"Generative Agents: Interactive Simulacra of Human Behavior"** (Park et al., 2023) | Agent memory streams, reflection, planning |
| **"MCP: Model Context Protocol"** (Anthropic, 2024) | MCP server integration pattern |

### Engineering Methodology

| Source | Application |
|--------|-------------|
| **Andrej Karpathy Guidelines for AI Engineering** | Quality control framework: Think Before / Simplicity First / Surgical Changes / Goal-Driven |
| **"The Cathedral and the Bazaar"** (Raymond, 1999) | Open-source development philosophy |
| **"Clean Architecture"** (Martin, 2017) | Modular architecture design principles |

---

## Cognitive Models Implemented

MemoryX implements the following cognitive architectures from psychology and neuroscience:

1. **Ebbinghaus Forgetting Curve** — Exponential decay of memory retention over time
2. **Baddeley Working Memory** — Phonological loop, visuospatial sketchpad, episodic buffer, central executive
3. **Kahneman Dual-Process** — System 1 (fast, intuitive) vs System 2 (slow, deliberate) retrieval
4. **Friston Free-Energy Principle** — Predictive coding and active inference for memory updating
5. **Sweller Cognitive Load** — Intrinsic, extraneous, and germane load management
6. **Squire-Zola Consolidation** — Memory replay and systems consolidation

---

## Individual Contributors

We thank all individuals who have contributed issues, code, documentation, or feedback to MemoryX and its upstream dependency projects.

---

## License Compliance

MemoryX is released under the MIT License. All referenced projects and papers are used for inspiration and design guidance only; no copyrighted code is copied directly unless explicitly attributed and licensed.