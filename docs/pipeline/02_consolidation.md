# 阶段2: 整合（Consolidation）

## 概述

整合阶段负责将新抽取的记忆与现有记忆进行合并、去重、冲突检测和关联，确保记忆库的一致性和准确性。

## 已实现模块

### 1. 整合引擎（Consolidation Engine）
**文件位置**: `memoryx/consolidation/`
**核心类**:
- `ConsolidationEngine`: 整合引擎主类
- `ConflictResolver`: 冲突检测器

### 2. 功能特性
- 语义去重
- 冲突检测与标记
- 记忆关联与链接
- 知识提炼与泛化
- 新旧记忆融合

## 处理流程

```
新抽取记忆 + 现有记忆
    ↓
相似度计算（语义+关键词）
    ↓
去重处理
    ↓
冲突检测
    ↓
冲突标记或解决
    ↓
记忆关联与链接
    ↓
知识提炼（可选）
    ↓
传递给下阶段（存储）
```

## Metrics定义

| Metric | 描述 | 目标值 | 测量方式 |
|--------|------|--------|----------|
| consolidation_latency | 单次整合耗时 | P95 < 300ms | 时间戳记录 |
| conflict_detection_accuracy | 冲突检测准确率 | ≥ 90% | 人工标注对比 |
| deduplication_rate | 去重率 | ≥ 20% | 去重计数 |
| link_count_per_memory | 平均每条记忆关联数 | ≥ 2 | 关联计数 |

## 配置项

| 配置项 | 默认值 | 描述 |
|--------|--------|------|
| consolidation.enabled | true | 是否启用自动整合 |
| consolidation.conflict_threshold | 0.7 | 冲突检测阈值 |
| consolidation.deduplication_threshold | 0.85 | 去重相似度阈值 |

## 示例代码

```python
from memoryx.consolidation import ConsolidationEngine
from memoryx.extraction import ExtractionMemory

# 初始化整合引擎
engine = ConsolidationEngine()

# 新记忆
new_memory = ExtractionMemory(
    content="用户喜欢Python",
    confidence_score=0.9
)

# 现有记忆
existing_memories = [
    ExtractionMemory(content="用户偏好Python语言", confidence_score=0.8),
    ExtractionMemory(content="用户不喜欢Java", confidence_score=0.7)
]

# 执行整合
result = engine.consolidate(new_memory, existing_memories)
if result.is_duplicate:
    print(f"发现重复: {result.duplicate_of}")
elif result.has_conflict:
    print(f"发现冲突: {result.conflict_with}")
else:
    print("可以安全存储")
```

## 相关文件

- `memoryx/consolidation/engine.py`: 整合引擎实现
- `memoryx/validation/conflict_resolver.py`: 冲突检测器
- `tests/unit/consolidation/`: 整合相关测试
