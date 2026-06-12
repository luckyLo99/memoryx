# MemoryX 基准测试指南

本指南介绍 MemoryX 的基准测试框架，包括 LongMemEval、BEAM 和竞争对比基准测试。

## 快速开始

### 运行所有基准测试

```bash
# 运行所有基准测试
python -m pytest tests/benchmarks/ -v -m benchmark

# 只运行 LongMemEval
python -m pytest tests/benchmarks/test_longmemeval.py -v

# 只运行 BEAM
python -m pytest tests/benchmarks/test_beam.py -v

# 运行竞争对比基准
python -m pytest tests/benchmarks/test_competitive_benchmark.py -v
```

## 基准测试概述

### 1. LongMemEval

**目标**: 评估长期记忆和跨会话推理能力

**测试场景**:
- 事实记忆召回
- 时序推理
- 冲突解决与知识更新

**性能目标**:
- 总体准确率 ≥ 60%
- P95 延迟 < 500ms

**运行方式**:
```bash
python -m pytest tests/benchmarks/test_longmemeval.py -v
```

### 2. BEAM (Benchmark for Evaluating Agent Memory)

**目标**: 生产规模的性能评估

**测试场景**:
- 大规模记忆存储 (1k - 1M 记录)
- 高并发检索延迟
- 吞吐量测试
- P50/P95/P99 延迟统计

**性能目标**:
- 写入吞吐量 > 100 ops/s
- P95 检索延迟 < 500ms
- 线性可扩展性

**运行方式**:
```bash
# 小规模测试 (快速)
python -m pytest tests/benchmarks/test_beam.py::test_beam_small_scale -v

# 大规模测试 (手动)
python -m pytest tests/benchmarks/test_beam.py::test_beam_large_scale -v --no-header
```

### 3. 竞争对比基准

**目标**: 与 Mem0、Letta、Zep 等主流系统对比

**对比维度**:
- 短期记忆准确率
- 冲突检测能力
- 会话隔离
- 遗忘曲线实现
- 上下文压缩

**运行方式**:
```bash
# 只运行 MemoryX 基准
python -m pytest tests/benchmarks/test_competitive_benchmark.py::test_benchmark_memoryx -v

# 运行所有 (需要第三方 API keys)
python -m pytest tests/benchmarks/test_competitive_benchmark.py -v
```

## 基准测试报告

所有基准测试都会生成 JSON 格式的报告，包含：
- 总体准确率/吞吐量
- 延迟统计 (P50/P95/P99)
- 详细的分项测试结果

报告位置: `{temp_dir}/{benchmark_name}_report.json`

## 添加新的基准测试

1. 在 `tests/benchmarks/` 创建新文件
2. 遵循现有结构创建测试类
3. 添加相应的 pytest marker
4. 实现测试逻辑和报告生成

示例:
```python
@pytest.mark.benchmark
@pytest.mark.my_benchmark
def test_my_benchmark():
    # 测试逻辑
    pass
```

## 性能调优建议

基于基准测试结果，可以：
1. 优化索引策略
2. 调整缓存大小
3. 优化查询逻辑
4. 调整批处理大小
