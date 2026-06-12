# 阶段3: 存储（Storage）

## 概述

存储阶段负责将经过整合的记忆持久化保存，支持多种后端存储方案，确保数据的安全、可靠和高效访问。

## 已实现模块

### 1. 存储库（Storage Repository）
**文件位置**: `memoryx/storage/`
**核心类**:
- `MemoryRepository`: 主存储库类
- `SQLiteAsync`: SQLite异步存储
- `LanceDBVectorStore`: 可选的向量数据库

### 2. 功能特性
- SQLite原生支持（FTS5全文检索）
- 可选向量数据库集成（LanceDB）
- 事务支持
- 数据备份与恢复
- 版本控制

## 处理流程

```
待存储记忆
    ↓
安全检查（PII过滤、防火墙）
    ↓
生成唯一ID
    ↓
元数据处理
    ↓
持久化（SQLite + 可选向量库）
    ↓
索引更新（FTS5 + 向量索引）
    ↓
审计日志记录
    ↓
完成确认
```

## Metrics定义

| Metric | 描述 | 目标值 | 测量方式 |
|--------|------|--------|----------|
| storage_write_latency | 单次写入耗时 | P95 < 100ms | 时间戳记录 |
| storage_read_latency | 单次读取耗时 | P95 < 50ms | 时间戳记录 |
| storage_throughput_write | 写入吞吐量 | ≥ 500次/分钟 | 计数器 |
| storage_index_size | 索引大小 | < 数据库50% | 存储大小 |

## 配置项

| 配置项 | 默认值 | 描述 |
|--------|--------|------|
| storage.backend | sqlite | 存储后端类型 |
| storage.db_path | memoryx.db | 数据库文件路径 |
| storage.vector_backend | none | 向量存储后端 |
| storage.backup_enabled | true | 是否启用备份 |

## 示例代码

```python
from memoryx.storage import MemoryRepository
from memoryx.extraction import ExtractionMemory

# 初始化存储库
repo = MemoryRepository("./memory.db")
await repo.open()

# 存储记忆
memory = ExtractionMemory(
    content="用户喜欢Python",
    confidence_score=0.9,
    importance_score=0.8
)
memory_id = await repo.store_memory(memory)

# 读取记忆
retrieved = await repo.get_memory(memory_id)

# 查询记忆
memories = await repo.query_memories(limit=10)
```

## 相关文件

- `memoryx/storage/repository.py`: 存储库实现
- `memoryx/storage/sqlite_async.py`: SQLite异步存储
- `memoryx/embeddings/lancedb_vector_store.py`: LanceDB向量存储
