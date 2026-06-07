# MemoryX — Cognitive Memory Operating System

> **Give your AI agent true production-grade cognitive memory: not just storage, but understanding, reflection, and self-optimization.**

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-993%20passed-brightgreen)](https://github.com/luckyl214/memoryx/actions)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen)](CONTRIBUTING.md)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000)](https://github.com/psf/black)
![Version](https://img.shields.io/badge/version-3.0.0-blue)

[English](#english) | [中文](#chinese)

---

## <a name="english"></a>English

MemoryX is a **production-grade cognitive memory operating system** designed for AI agents. Unlike simple key-value stores or vector databases, MemoryX implements multiple cognitive science models to provide **human-like memory capabilities**:

- Multi-layer memory hierarchy (working -> short-term -> long-term -> consolidated -> archive)
- Hybrid retrieval with 6 channels (semantic vector + keyword/FTS5 + temporal + entity + importance + episodic)
- Ebbinghaus forgetting curve for biologically-plausible decay
- Baddeley working memory model (phonological loop, visuospatial sketchpad, episodic buffer)
- Dual-process retrieval (System 1 fast / System 2 deliberate)
- Predictive coding and active inference for self-correcting memory
- Event-driven architecture with async hooks system
- Native Hermes Agent integration
- MCP (Model Context Protocol) server

### Key Features

#### Cognitive Architecture
| Layer | Classification | Retention |
|-------|---------------|-----------|
| **Working Memory** | Current conversation | Real-time reasoning context |
| **Short-term Episodic** | EPISODIC type | Recent events (hours) |
| **Long-term Semantic** | importance >= 0.85 OR access_count >= 3 | Persistent knowledge (days) |
| **Consolidated Knowledge** | Medium importance | Stable knowledge (weeks) |
| **Archive** | decay >= 0.9 AND access_count = 0 | Cold storage (indefinite) |

#### Hybrid 6-Channel Retrieval
| Channel | Weight | Purpose |
|---------|--------|---------|
| Semantic Vector | 1.0 | Understanding meaning |
| Keyword (FTS5/BM25) | 1.0 | Precision matching |
| Temporal Decay | 0.45 | Freshness scoring |
| Entity Relationship | 0.35 | Associative reasoning |
| Importance | 0.6 | Priority ranking |
| Episodic Context | 0.4 | Situational awareness |

#### Event-Driven Hook System
```
5 event types:
  - on_user_message
  - on_assistant_response
  - on_tool_call
  - on_tool_result
  - on_session_end
```

### Quick Start

```bash
# Install
pip install memoryx

# Or from source
git clone https://github.com/luckyl214/memoryx.git
cd memoryx
pip install -e .

# Run self-check
memoryx doctor

# Run tests
pytest -q
```

### Hermes Agent Integration

MemoryX provides a native integration path for [Hermes Agent](https://github.com/NousResearch/hermes-agent):

```python
from memoryx.hermes.provider import MemoryXHermesProvider
from memoryx.hermes.bridge import HermesMemoryBridge
from memoryx.storage.repository import MemoryRepository

repo = MemoryRepository("./memory.db")
await repo.open()
bridge = HermesMemoryBridge(repository=repo)
provider = MemoryXHermesProvider(bridge=bridge)

# Use as Hermes tool
result = await provider.handle_tool_call("memory", {
    "action": "add",
    "content": "User prefers Python for data analysis"
})
```

See [`docs/HERMES_MEMORYX_AUTHORITATIVE.md`](docs/HERMES_MEMORYX_AUTHORITATIVE.md) for full integration guide.

### MCP Server

```bash
memoryx-mcp  # Starts MCP server for Model Context Protocol clients
```

### Project Status

**Version 3.0.0** — 993 tests passing, 0 failing. Active development with a focus on cognitive architecture research and production reliability.

---

## <a name="chinese"></a>中文

MemoryX（记忆女神 X）是一个**生产级的认知记忆操作系统**，专为 AI Agent 设计。与简单的键值存储或向量数据库不同，MemoryX 实现了多种认知科学模型，提供了**类人记忆能力**：

- 多层记忆层级（工作记忆 → 短期事件 → 长期知识 → 固化的知识 → 归档）
- 6 通道混合检索（语义向量 + 关键词/FTS5 + 时序 + 实体关系 + 重要性 + 情节上下文）
- Ebbinghaus 遗忘曲线，实现生物学上合理的衰减
- Baddeley 工作记忆模型（语音回路、视空间画板、情景缓冲区）
- 双过程检索（系统 1 快速直觉 / 系统 2 审慎推理）
- 预测编码与主动推断，实现自我修正的记忆
- 事件驱动架构与异步钩子系统
- 原生 Hermes Agent 集成
- MCP（模型上下文协议）服务器

### 核心特性

#### 认知架构
| 层级 | 分类标准 | 用途 |
|------|---------|------|
| **工作记忆** | 当前会话 | 实时推理上下文 |
| **短期情景** | EPISODIC 类型 | 近期事件（小时级） |
| **长期语义** | importance >= 0.85 或 access_count >= 3 | 持久知识（天级） |
| **固化知识** | 中等重要性 | 稳定知识（周级） |
| **归档** | decay >= 0.9 且 access_count = 0 | 冷存储（长期） |

#### 6 通道混合检索
| 通道 | 权重 | 用途 |
|------|------|------|
| 语义向量 | 1.0 | 理解含义 |
| 关键词 FTS5/BM25 | 1.0 | 精确匹配 |
| 时序衰减 | 0.45 | 新鲜度评分 |
| 实体关系 | 0.35 | 关联推理 |
| 重要性 | 0.6 | 优先级排序 |
| 情节上下文 | 0.4 | 情景感知 |

### 快速开始

```bash
# 安装
pip install memoryx

# 或从源码安装
git clone https://github.com/luckyl214/memoryx.git
cd memoryx
pip install -e .

# 运行自检
memoryx doctor

# 运行测试
pytest -q
```

### Hermes Agent 集成

MemoryX 为 Hermes Agent 提供原生集成路径：

```python
from memoryx.hermes.provider import MemoryXHermesProvider
from memoryx.hermes.bridge import HermesMemoryBridge
from memoryx.storage.repository import MemoryRepository

repo = MemoryRepository("./memory.db")
await repo.open()
bridge = HermesMemoryBridge(repository=repo)
provider = MemoryXHermesProvider(bridge=bridge)

# 作为 Hermes 工具使用
result = await provider.handle_tool_call("memory", {
    "action": "add",
    "content": "用户偏好 Python 进行数据分析"
})
```

完整集成指南请参阅 [`docs/HERMES_MEMORYX_AUTHORITATIVE.md`](docs/HERMES_MEMORYX_AUTHORITATIVE.md)。

### 项目状态

**版本 3.0.0** — 993 项测试通过，0 项失败。正在积极开发中，重点关注认知架构研究和生产可靠性。

---

## Architecture

```
User Input
    |
    v
Hermes Agent
    |
    v
MemoryXHermesProvider  ----> MCP Server (external clients)
    |                              |
    v                              v
HermesMemoryBridge          MCP Tools
    |                              |
    v                              v
MemoryCandidateService
    |
    v
+----------------------------+
|    Storage Layer           |
|  MemoryRepository          |
|    |                       |
|    +-> SQLite (FTS5)       |
|    +-> Optional Vector DB  |
|    +-> Version History     |
+----------------------------+
    |
    v
+----------------------------+
|    Retrieval Engine        |
|  HybridRetrievalEngine     |
|    |                       |
|    +-> 6-Channel Scoring   |
|    +-> Dual-Process        |
|    +-> Ebbinghaus Decay    |
+----------------------------+
    |
    v
+----------------------------+
|    Cognitive Modules       |
|  Working Memory (Baddeley) |
|  Dual-Process (Kahneman)   |
|  Predictive Coding         |
|  Cognitive Load            |
|  Procedural Memory         |
+----------------------------+
    |
    v
Context Injection --> Agent Response
```

## Documentation

| Topic | Location |
|-------|----------|
| Hermes Integration | [docs/HERMES_MEMORYX_AUTHORITATIVE.md](docs/HERMES_MEMORYX_AUTHORITATIVE.md) |
| Cognitive Models | [docs/cognitive/](docs/cognitive/) |
| Competitive Analysis | [docs/competitive_analysis.md](docs/competitive_analysis.md) |
| API Reference | [docs/](docs/) |
| Contributing | [CONTRIBUTING.md](CONTRIBUTING.md) |
| Changelog | [CHANGELOG.md](CHANGELOG.md) |
| Credits | [CREDITS.md](CREDITS.md) |

## License

MIT License — see [LICENSE](LICENSE) for details.

---

*MemoryX is part of the [Codex for OSS](https://openai.com/zh-Hans-CN/form/codex-for-oss/) program, using AI-assisted development to build better cognitive memory for intelligent agents.*