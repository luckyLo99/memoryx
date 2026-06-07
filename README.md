<div align="center">

# 🧠 MemoryX — Cognitive Memory Operating System

**Production-grade long-term memory for AI agents — Ebbinghaus decay, Baddeley working memory, dual-process retrieval, and native Hermes Agent integration.**

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue?style=flat-square&logo=python)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-993%20passed-brightgreen?style=flat-square)](https://github.com/luckyl214/memoryx/actions)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen?style=flat-square)](CONTRIBUTING.md)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000?style=flat-square)](https://github.com/psf/black)
[![Version](https://img.shields.io/badge/version-3.0.0-blue?style=flat-square)](https://github.com/luckyl214/memoryx/releases)

</div>

---

<details open>
<summary><b>🇬🇧 English</b></summary>

MemoryX is a **production-grade cognitive memory operating system** designed for AI agents. Unlike simple key-value stores or vector databases, MemoryX implements **six cognitive science models** to provide human-like memory capabilities:

- **🧠 Ebbinghaus Forgetting Curve** — Biologically-plausible exponential decay with spaced repetition
- **🗂️ Baddeley Working Memory** — Phonological loop, visuospatial sketchpad, episodic buffer
- **⚡ Dual-Process Retrieval** — System 1 (fast/intuitive) vs System 2 (slow/deliberate)
- **🔮 Predictive Coding** — Active inference and free-energy principle for self-correcting memory
- **📊 Cognitive Load Optimization** — Intrinsic/extraneous/germane load management
- **🔄 Procedural Memory** — Skill learning, pattern recognition, automaticity

### Architecture

```
User Input → Hermes Agent → MemoryXHermesProvider → HermesMemoryBridge
                                                            ↓
                                              MemoryCandidateService
                                                            ↓
                                ┌───────────────────────────────┐
                                │      HybridRetrievalEngine    │
                                │  6-Channel Scoring + Dual-    │
                                │  Process + Ebbinghaus Decay   │
                                └───────────────────────────────┘
                                ┌───────────────────────────────┐
                                │      Storage Layer            │
                                │  MemoryRepository             │
                                │  SQLite (FTS5) + Vector DB    │
                                └───────────────────────────────┘
                                ┌───────────────────────────────┐
                                │      Cognitive Modules        │
                                │  Baddeley · Kahneman ·        │
                                │  Friston · Sweller · Squire   │
                                └───────────────────────────────┘
                                                            ↓
                                              Context Injection
                                                            ↓
                                              Agent Response
```

### Quick Start

```bash
pip install memoryx
# Or from source:
git clone https://github.com/luckyl214/memoryx.git && cd memoryx && pip install -e .
memoryx doctor        # Run self-check
pytest -q             # Run 993 tests
```

### Hermes Agent Integration

```python
from memoryx.hermes.provider import MemoryXHermesProvider
from memoryx.hermes.bridge import HermesMemoryBridge
from memoryx.storage.repository import MemoryRepository

repo = MemoryRepository("./memory.db")
await repo.open()
provider = MemoryXHermesProvider(bridge=HermesMemoryBridge(repository=repo))

# Store a memory
result = await provider.handle_tool_call("memory", {
    "action": "add",
    "content": "User prefers Python for data analysis"
})
```

### Key Metrics

| Metric | Value |
|--------|-------|
| Tests | 993 passed, 0 failing |
| Cognitive Models | 6 (Ebbinghaus, Baddeley, Kahneman, Friston, Sweller, Squire) |
| Retrieval Channels | 6 (Vector + Keyword + Temporal + Entity + Importance + Episodic) |
| Memory Layers | 5 (Working → Short-term → Long-term → Consolidated → Archive) |
| Offline | Full (zero external dependencies) |
| Hermes Integration | Native bridge + provider + MCP server |

---

</details>

<details>
<summary><b>🇨🇳 中文</b></summary>

MemoryX（记忆女神 X）是一个**生产级的认知记忆操作系统**，专为 AI Agent 设计。与简单的键值存储或向量数据库不同，MemoryX 实现了**六种认知科学模型**，提供类人记忆能力：

- **🧠 Ebbinghaus 遗忘曲线** — 基于生物学的指数衰减与间隔重复
- **🗂️ Baddeley 工作记忆** — 语音回路、视空间画板、情景缓冲区
- **⚡ 双过程检索** — 系统 1（快速直觉）与系统 2（审慎推理）
- **🔮 预测编码** — 主动推断与自由能原理，实现自我修正
- **📊 认知负荷优化** — 内在/外在/相关负荷管理
- **🔄 程序性记忆** — 技能学习、模式识别、自动化

### 核心架构

```
用户输入 → Hermes Agent → MemoryXHermesProvider → HermesMemoryBridge
                                                            ↓
                                              MemoryCandidateService
                                                            ↓
                                ┌───────────────────────────────┐
                                │      HybridRetrievalEngine    │
                                │  6 通道评分 + 双过程检索      │
                                │  + Ebbinghaus 衰减            │
                                └───────────────────────────────┘
                                ┌───────────────────────────────┐
                                │      存储层                   │
                                │  MemoryRepository             │
                                │  SQLite (FTS5) + 向量数据库   │
                                └───────────────────────────────┘
                                ┌───────────────────────────────┐
                                │      认知模块                 │
                                │  Baddeley · Kahneman ·        │
                                │  Friston · Sweller · Squire   │
                                └───────────────────────────────┘
                                                            ↓
                                              上下文注入
                                                            ↓
                                              Agent 响应
```

### 快速开始

```bash
pip install memoryx
# 或从源码安装：
git clone https://github.com/luckyl214/memoryx.git && cd memoryx && pip install -e .
memoryx doctor        # 运行自检
pytest -q             # 运行 993 项测试
```

### Hermes Agent 集成

```python
from memoryx.hermes.provider import MemoryXHermesProvider
from memoryx.hermes.bridge import HermesMemoryBridge
from memoryx.storage.repository import MemoryRepository

repo = MemoryRepository("./memory.db")
await repo.open()
provider = MemoryXHermesProvider(bridge=HermesMemoryBridge(repository=repo))

# 存储记忆
result = await provider.handle_tool_call("memory", {
    "action": "add",
    "content": "用户偏好 Python 进行数据分析"
})
```

### 核心指标

| 指标 | 数据 |
|------|------|
| 测试 | 993 通过，0 失败 |
| 认知模型 | 6 个（Ebbinghaus、Baddeley、Kahneman、Friston、Sweller、Squire） |
| 检索通道 | 6 个（向量 + 关键词 + 时序 + 实体 + 重要性 + 情节） |
| 记忆层级 | 5 层（工作 → 短期 → 长期 → 固化 → 归档） |
| 离线能力 | 完整（零外部依赖） |
| Hermes 集成 | 原生桥接 + Provider + MCP 服务器 |

</details>

---

## 📚 Documentation

| Topic | Link |
|-------|------|
| Hermes Integration Guide | [docs/HERMES_MEMORYX_AUTHORITATIVE.md](docs/HERMES_MEMORYX_AUTHORITATIVE.md) |
| Cognitive Model Docs | [docs/cognitive/](docs/cognitive/) |
| Competitive Analysis | [docs/competitive_analysis.md](docs/competitive_analysis.md) |
| API Reference | [docs/](docs/) |
| Changelog | [CHANGELOG.md](CHANGELOG.md) |
| Credits & Citations | [CREDITS.md](CREDITS.md) |
| Contributing Guide | [CONTRIBUTING.md](CONTRIBUTING.md) |

## 📦 Installation Profiles

```bash
pip install memoryx                 # Minimal (default)
pip install memoryx[vector]         # + Vector search (LanceDB + sentence-transformers)
pip install memoryx[mcp]            # + MCP server
pip install memoryx[dev]            # + Development tools
```

## 🏆 Competitive Advantages

| Feature | MemoryX | Mem0 | Letta | Zep |
|---------|---------|------|-------|-----|
| Offline | ✅ Full | ❌ Cloud | ❌ Cloud | ⚠️ Limited |
| Cognitive Models | 6 models | Basic | None | None |
| Hermes Native | ✅ Yes | ❌ No | ❌ No | ❌ No |
| MCP Server | ✅ Built-in | ❌ No | ❌ No | ❌ No |
| PII Filter | ✅ Yes | ❌ No | ❌ No | ❌ No |
| Session Isolation | ✅ Native | ⚠️ API | ❌ No | ⚠️ API |
| Open Source | ✅ MIT | ✅ Apache | ✅ Apache | ✅ MIT |

## 🤝 Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines. This project follows the Karpathy Engineering Guidelines.

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.

---

<div align="center">

*Built with ❤️ for the AI agent community. Part of the [Codex for OSS](https://openai.com/zh-Hans-CN/form/codex-for-oss/) program.*

⭐ Star us on GitHub — it helps other developers find MemoryX!

</div>