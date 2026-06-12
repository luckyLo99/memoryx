# 阶段5: 遗忘（Forgetting）

## 概述

遗忘阶段负责主动管理记忆库的生命周期，删除或归档不再有用的记忆，保持系统性能和记忆质量。

## 已实现模块

### 1. 认知模型（Cognitive Models）
**文件位置**: `memoryx/cognitive/`
**核心类**:
- `EbbinghausForgetting`: 艾宾浩斯遗忘曲线实现
- `WorkingMemory`: 工作记忆管理
- `DualProcessRetrieval`: 双过程检索

### 2. 功能特性
- 艾宾浩斯遗忘曲线
- 重要性加权遗忘
- 访问频率考虑
- 记忆归档而非删除
- 定期清理任务

## 处理流程

```
记忆库扫描
    ↓
计算遗忘分数（Ebbinghaus + 重要性 + 访问频率）
    ↓
识别待遗忘记忆
    ↓
用户确认/策略评估
    ↓
执行遗忘（归档或软删除）
    ↓
更新索引
    ↓
记录遗忘日志
```

## 艾宾浩斯遗忘曲线

记忆强度随时间衰减公式：

```
R = e^(-t/S)
```

其中：
- R: 记忆保持率
- t: 时间间隔
- S: 记忆强度（由重要性、访问频率等决定）

## Metrics定义

| Metric | 描述 | 目标值 | 测量方式 |
|--------|------|--------|----------|
| forgetting_rate | 月均遗忘率 | 5-15% | 月统计 |
| archive_size | 归档记忆占比 | < 20% | 存储统计 |
| memory_utility | 记忆效用评分 | ≥ 0.6 | 回访率计算 |
| storage_efficiency | 存储效率 | 提升10%/季度 | 存储统计 |

## 遗忘策略

| 策略 | 描述 | 适用场景 |
|------|------|----------|
| TIME_BASED | 基于时间的遗忘 | 所有记忆 |
| IMPORTANCE_WEIGHTED | 重要性加权遗忘 | 优先保留重要记忆 |
| ACCESS_FREQUENCY | 访问频率遗忘 | 优先保留高频访问 |
| COGNITIVE_LOAD | 认知负载优化 | 系统负载高时 |

## 配置项

| 配置项 | 默认值 | 描述 |
|--------|--------|------|
| forgetting.enabled | true | 是否启用自动遗忘 |
| forgetting.strategy | IMPORTANCE_WEIGHTED | 遗忘策略 |
| forgetting.threshold | 0.3 | 遗忘阈值 |
| forgetting.archive_enabled | true | 是否启用归档 |

## 示例代码

```python
from memoryx.cognitive import EbbinghausForgetting
from memoryx.storage import MemoryRepository

# 初始化
repo = MemoryRepository("./memory.db")
await repo.open()
forgetting = EbbinghausForgetting()

# 计算遗忘分数
memory = await repo.get_memory(memory_id)
score = forgetting.calculate_forgetting_score(memory)

if score < 0.3:  # 低于阈值，考虑遗忘
    await forgetting.archive_memory(memory_id)
    print("记忆已归档")
```

## 相关文件

- `memoryx/cognitive/ebbinghaus.py`: 遗忘曲线实现
- `memoryx/cognitive/working_memory.py`: 工作记忆
- `memoryx/retrieval/scorer.py`: 评分器（包含遗忘计算）
