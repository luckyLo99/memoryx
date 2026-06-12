# 阶段4: 检索（Retrieval）

## 概述

检索阶段负责根据用户查询或Agent需求，从记忆库中找到最相关、最有价值的记忆信息，用于上下文注入和决策支持。

## 已实现模块

### 1. 检索引擎（Retrieval Engine）
**文件位置**: `memoryx/retrieval/`
**核心类**:
- `HybridRetriever`: 混合检索器
- `RetrievalEngine`: 检索引擎主类
- 多种评分器：Ebbinghaus、时间、重要性等

### 2. 功能特性
- 6通道混合检索（语义+BM25+时间+实体+重要性+情节）
- 混合重排序
- 上下文预算管理
- 自适应检索策略
- 缓存优化

## 处理流程

```
用户查询/Agent需求
    ↓
查询理解与意图识别
    ↓
多通道并行检索
    │
    ├─ 语义向量检索
    ├─ BM25关键词检索
    ├─ 时间相关性检索
    ├─ 实体关联检索
    ├─ 重要性评分检索
    └─ 情节记忆检索
    ↓
结果合并与去重
    ↓
混合重排序
    ↓
上下文预算裁剪
    ↓
记忆过滤（安全+时效性）
    ↓
返回上下文
```

## Metrics定义

| Metric | 描述 | 目标值 | 测量方式 |
|--------|------|--------|----------|
| retrieval_latency | 单次检索耗时 | P95 < 500ms | 时间戳记录 |
| retrieval_precision | 检索准确率 | ≥ 80% | 人工标注对比 |
| retrieval_recall | 检索召回率 | ≥ 75% | 人工标注对比 |
| context_relevance | 上下文相关性 | ≥ 0.7 | 用户反馈 |

## 6通道评分权重

| 通道 | 权重 | 描述 |
|------|------|------|
| 语义相似度 | 0.35 | 向量余弦相似度 |
| BM25关键词 | 0.20 | 关键词匹配度 |
| 时间相关性 | 0.15 | 新鲜度评分 |
| 实体关联 | 0.10 | 实体重叠度 |
| 重要性 | 0.10 | 记忆重要性 |
| 情节记忆 | 0.10 | 上下文连贯性 |

## 配置项

| 配置项 | 默认值 | 描述 |
|--------|--------|------|
| retrieval.limit | 20 | 默认返回记忆数 |
| retrieval.semantic_weight | 0.35 | 语义通道权重 |
| retrieval.cache_enabled | true | 是否启用缓存 |
| retrieval.budget_tokens | 4096 | 上下文Token预算 |

## 示例代码

```python
from memoryx.retrieval import RetrievalEngine
from memoryx.storage import MemoryRepository

# 初始化
repo = MemoryRepository("./memory.db")
await repo.open()
engine = RetrievalEngine(repository=repo)

# 检索记忆
query = "用户喜欢什么编程语言？"
results = await engine.retrieve(
    query=query,
    limit=10,
    context_budget=2048
)

for result in results:
    print(f"记忆: {result.content}")
    print(f"评分: {result.score}")
```

## 相关文件

- `memoryx/retrieval/engine.py`: 检索引擎实现
- `memoryx/retrieval/fusion.py`: 结果融合
- `memoryx/retrieval/scorer.py`: 评分器实现
- `memoryx/core/hybrid_retriever.py`: 混合检索器
