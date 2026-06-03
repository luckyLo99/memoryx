# memoryx — 认知记忆操作系统

> Hermes users: for the verified MemoryX authoritative integration, see [`docs/HERMES_MEMORYX_AUTHORITATIVE.md`](docs/HERMES_MEMORYX_AUTHORITATIVE.md). This documents the MemoryX provider, the authoritative native `memory()` patch, verification, and post-Hermes-update recovery steps.


> **让 Agent 拥有真正的生产级认知记忆：不仅记住，还能理解、反思和自我优化。**

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-827%20passed-brightgreen)](https://github.com/luckyl214/memoryx/actions)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen)](CONTRIBUTING.md)

---

## 📖 目录

- [简介](#简介)
- [核心特性](#核心特性)
- [快速开始](#快速开始)
- [Hermes Agent 集成](#hermes-agent-集成)
- [架构设计](#架构设计)
- [API 参考](#api-参考)
- [开发指南](#开发指南)
- [常见问题](#常见问题)
- [许可证](#许可证)

---

## 简介

memoryx（记忆女神 X）是一个**生产级的认知记忆操作系统**，专为 AI Agent 设计。它不仅仅是存储和检索记忆，而是提供：

- **多层级记忆存储**：工作记忆 → 短期事件 → 长期知识 → 归档
- **混合检索引擎**：向量 + 关键词 + 时序 + 实体关系 + 重要性
- **事件驱动架构**：基于 EventBus 的异步钩子系统
- **自修复能力**：崩溃恢复、数据一致性验证
- **资源治理**：适配 2C4G 等低配环境

---

## 核心特性

### 🏛️ 五层记忆层级

| 层级 | 分类标准 | 用途 |
|------|---------|------|
| **Working** | 当前会话 | 实时推理态 |
| **Short-term Episodic** | EPISODIC 类型 | 近期事件 |
| **Long-term Semantic** | importance ≥ 0.85 OR access_count ≥ 3 | 持久知识 |
| **Consolidated Knowledge** | 中等重要性默认 | 稳定知识 |
| **Archive** | decay ≥ 0.9 AND access_count = 0 | 冷存储 |

### 🎯 Palace 可导航存储

受 MemPalace 启发的层次化导航系统。记忆不仅可搜索，还可像建筑一样步进浏览：

```
Wing (记忆类型) → Room (主题) → Drawer (具体记忆)
```

### 🔍 6 通道混合检索

| 通道 | 权重 | 用途 |
|------|------|------|
| 语义向量 | 1.0 | 理解含义 |
| 关键词 BM25/FTS5 | 1.0 | 精确匹配 |
| 时序衰减 | 0.45 | 新鲜度 |
| 实体关系 | 0.35 | 关联推理 |
| 重要性 | 0.6 | 优先级 |
| 情节 | 0.4 | 上下文 |

### 📡 事件驱动钩子系统

```
5 事件类型:
  - on_user_message
  - on_assistant_response
  - on_tool_call
  - on_tool_result
  - on_session_end

5 优先级: CRITICAL=0 → HIGH=10 → NORMAL=20 → LOW=30 → BACKGROUND=40

功能:
  - DLQ (死信队列)
  - 队列持久化
  - 崩溃恢复
  - 健康指标
  - 追踪 ID
```

---

## 快速开始

### 1. 安装

```bash
# 克隆仓库
git clone https://github.com/luckyl214/memoryx.git
cd memoryx

# 切换到 stable 版本
git checkout v2.0.0

# 创建虚拟环境
python3 -m venv .venv
source .venv/bin/activate

# 安装依赖（选择其一）
# Lite (no embedding / can run without vector dependencies)
# pip install -e .
#
# Standard (with embedding support)
# pip install -e ".[embedding]"
#
# Development (includes test dependencies)
# pip install -e ".[dev]"
```

### 2. 配置

```bash
# 复制环境变量模板
cp .env.example .env

# 编辑配置（至少需要 Embedding API）
# .env (choose one of the profile templates from .env.example):
#   # Example for standard profile:
#   MEMORYX_PROFILE=standard
#   MEMORYX_VECTOR_ENABLED=true
#   MEMORYX_EMBEDDING_ENABLED=true
#   MEMORYX_EMBEDDING_ENDPOINT=https://api.openai.com/v1/embeddings
#   MEMORYX_EMBEDDING_API_KEY=your_api_key_here
#   MEMORYX_EMBEDDING_MODEL=text-embedding-3-small
```

### 3. 验证安装

```bash
# 运行验证脚本（检查检索、记忆、对话日志等核心功能）
python3 scripts/verify_memoryx.py
```

### 4. 基本使用

```python
from pathlib import Path
import asyncio
from memoryx.storage.repository import MemoryRepository, MemoryRecord

async def main():
    # 初始化仓库（自动创建数据库）
    repo = MemoryRepository(db_path=Path("./memoryx_lite.db"))
    await repo.open()

    # 存储记忆
    record = MemoryRecord(
        memory_id="user_preference_001",
        content="用户偏好简洁回答",
        memory_type="FACT",
        importance_score=0.8
    )
    mid = await repo.store_memory(record)
    print(f"Stored: {mid}")

    # FTS 全文检索
    results = await repo.search_full_text("简洁")
    for r in results:
        print(f"[{r.get('memory_type', '?')}] {r.get('content', '')}")

    await repo.close()

asyncio.run(main())
```

---

## Hermes Agent 集成

For the verified Hermes authoritative integration, see [`docs/HERMES_MEMORYX_AUTHORITATIVE.md`](docs/HERMES_MEMORYX_AUTHORITATIVE.md).

MemoryX supports Hermes through two separate pieces:

1. A Hermes MemoryX provider.
2. An authoritative patch that routes native Hermes `memory()` writes into MemoryX.

The runtime hook/plugin path is not a replacement for the Hermes native memory provider. For production Hermes usage, follow the authoritative integration document above.


## 架构设计

```
                    Hermes Agent (消息管道 / 工具调用)
                              │
                    ┌─────────▼─────────┐
                    │   EventBus + DLQ  │  事件驱动中枢
                    │   优先级队列/追踪   │
                    └─────────┬─────────┘
                              │
         ┌────────────────────┼────────────────────┐
         ▼                    ▼                    ▼
    Extractor           Retriever            Injector
   (L1 记忆提取)      (6 通道混合检索)      (上下文注入)
         │                    │                    │
         └────────────────────┼────────────────────┘
                              ▼
                    ┌─────────────────────┐
                    │    Memory Store      │  SQLite + FTS5 + WAL
                    │    (22 表，多层)     │  LanceDB 向量
                    └─────────────────────┘
                              │
         ┌────────────────────┼────────────────────┐
         ▼                    ▼                    ▼
   PalaceEngine        SelfHealing          ResourceGovernance
   (可导航层次存储)     (自修复/崩溃恢复)      (2C4G 资源治理)
         │                    │                    │
         └────────────────────┼────────────────────┘
                              ▼
                    ┌─────────────────────┐
                    │  ModuleRegistry +    │  全局模块编排
                    │  SystemOrchestrator  │  (健康检查/依赖管理)
                    └─────────────────────┘
```

---

## API 参考

### MemoryRepository

```python
# 打开仓库（自动创建数据库）
repo = MemoryRepository.open()

def store_memory(record: MemoryRecord) -> str: ...
def search_full_text(query: str, limit: int = 20) -> list[dict]: ...
def search_memories_text(
    query: str,
    limit: int = 20,
    include_states: set[str] | None = None,
) -> list[dict]: ...
def list_memories(limit: int = 1000) -> list[dict]: ...
def update_memory_metadata(memory_id: str, metadata_patch: dict) -> bool: ...
def supersede_memory(memory_id: str, superseded_by: str) -> None: ...
```

### HybridRetrievalEngine

```python
from memoryx.retrieval import HybridRetrievalEngine

engine = HybridRetrievalEngine(repository=repo)

async def retrieve(
    *,
    query: str,
    limit: int = 10,
    tag_filter: list[str] | None = None,
    scope_filter: str | None = None,
    session_id: str | None = None,
    explain_scores: bool = False,
    fusion_method: str = "weighted",
) -> list[RetrievalResult]: ...

# 获取可解释评分
for r in results:
    print(f"语义: {r.semantic_score}, 关键词: {r.keyword_score}, "
          f"实体: {r.entity_score}, 时序: {r.temporal_score}, "
          f"重要性: {r.importance_score}, 情节: {r.episodic_score}, "
          f"最终: {r.final_score}")
```

### ConversationLogStore

```python
from memoryx.conversation_log import ConversationLogStore

log_store = ConversationLogStore(repo)

async def log(session_id: str, role: str, content: str) -> str: ...
async def session_history(session_id: str, *, limit: int = 50) -> list[dict]: ...
async def search(query: str, *, session_id: str | None = None, limit: int = 20) -> list[dict]: ...
```

---

## 开发指南

### 添加新模块

```
module/
├── __init__.py    # 导出
├── engine.py      # 主实现
├── models.py      # 数据模型
└── tests/         # 测试
    └── test_module.py
```

### 运行测试

```bash
# 全部测试
pytest -q

# 定向测试
pytest -q tests/test_storage.py

# 带覆盖率
pytest --cov=memoryx --cov-report=html
```

### 代码风格

- Python 3.11+ type hints 必须
- async/await 优先
- 无 ORM，无重量级框架
- 所有 API 调用必须 retry + timeout + backoff
- 所有 IO 必须 async

---

## 常见问题

### Q: 为什么需要记忆系统？

A: 现代 AI Agent 需要在多次对话中保持上下文一致性。记忆系统让 Agent：
- 记住用户偏好和历史
- 跨会话保持连续性
- 自我反思和优化

### Q: 支持哪些数据库？

A: 当前支持 SQLite（生产推荐，WAL + FTS5）和 LanceDB（向量存储）。计划支持：
- PostgreSQL（大规模）
- Redis（缓存层）

### Q: 如何迁移现有记忆？

A: 使用迁移脚本：

```bash
# 从 LanceDB 格式导入
python3 scripts/migrate_to_lancedb.py
```

### Q: 性能如何？

A: 内部基准（2C4G VPS，1000 条记忆）：
- 检索延迟：约 50ms
- 存储吞吐：约 100 ops/s
- 内存占用：约 200MB
（实际性能因 Embedding 模型和存储介质而异）

### Q: 如何验证安装是否正常？

A: 运行验证脚本：

```bash
python3 scripts/verify_memoryx.py
```

该脚本会测试存储、全文检索、混合检索、对话日志等核心功能是否正常。

---

## 许可证

MIT License - 详见 [LICENSE](LICENSE) 文件。

---

## 贡献

欢迎贡献！详见 [CONTRIBUTING.md](CONTRIBUTING.md)。

---

## 联系

- GitHub Issues: https://github.com/luckyl214/memoryx/issues
- 文档: https://github.com/luckyl214/memoryx/tree/main/docs
