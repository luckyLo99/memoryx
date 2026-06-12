# 阶段1: 抽取（Extraction）

## 概述

抽取阶段负责从用户输入、对话历史、Agent执行结果等原始数据中识别并提取有价值的记忆信息。

## 已实现模块

### 1. 抽取引擎（Extraction Engine）
**文件位置**: `memoryx/extraction/`
**核心类**:
- `ExtractionMemory`: 抽取记忆的数据结构
- `ExtractionEngine`: 抽取引擎主类

### 2. 功能特性
- 从对话中自动提取关键信息
- 支持用户偏好、事实、任务等不同类型记忆
- 置信度评分机制
- 时间戳记录

## 处理流程

```
用户输入/对话历史
    ↓
预处理（去重、格式标准化）
    ↓
关键信息识别（实体、事件、偏好）
    ↓
信息分类与打标
    ↓
置信度计算
    ↓
生成ExtractionMemory对象
    ↓
传递给下阶段（整合）
```

## Metrics定义

| Metric | 描述 | 目标值 | 测量方式 |
|--------|------|--------|----------|
| extraction_latency | 单次抽取耗时 | P95 < 200ms | 时间戳记录 |
| extraction_accuracy | 抽取准确率 | ≥ 85% | 人工标注对比 |
| extraction_throughput | 吞吐量 | ≥ 100次/分钟 | 计数器 |
| extraction_duplicate_rate | 重复抽取率 | < 5% | 去重检查 |

## 配置项

| 配置项 | 默认值 | 描述 |
|--------|--------|------|
| extraction.enabled | true | 是否启用自动抽取 |
| extraction.confidence_threshold | 0.6 | 最低置信度阈值 |
| extraction.deduplication | true | 是否启用去重 |

## 示例代码

```python
from memoryx.extraction import ExtractionEngine, ExtractionMemory

# 初始化抽取引擎
engine = ExtractionEngine()

# 从对话中抽取记忆
dialog_history = [
    {"role": "user", "content": "我喜欢用Python进行数据分析"},
    {"role": "user", "content": "我住在北京"}
]

memories = engine.extract_from_dialog(dialog_history)
for memory in memories:
    print(f"内容: {memory.content}")
    print(f"置信度: {memory.confidence_score}")
```

## 相关文件

- `memoryx/extraction/engine.py`: 抽取引擎实现
- `memoryx/extraction/models.py`: 数据模型
- `tests/unit/extraction/`: 抽取相关测试
