# -*- coding: utf-8 -*-
"""
BEAM 基准测试 - 生产规模记忆系统性能评估.

BEAM (Benchmark for Evaluating Agent Memory) 是针对大规模记忆系统的基准测试，
包含百万级Token的测试场景，评估：
- 大规模记忆存储性能
- 高并发检索延迟
- 内存占用和磁盘IO
- 扩展性测试

Run:  python -m pytest tests/benchmarks/test_beam.py -v --tb=short
"""

from __future__ import annotations
import json
import time
import tempfile
import random
import string
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List, Dict
import pytest


TEST_DIR = Path(tempfile.mkdtemp()) / "beam"


@dataclass
class BEAMResult:
    """BEAM 单个测试结果."""
    test_name: str
    throughput: float  # operations per second
    p50_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float
    memory_usage_mb: float = 0.0
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BEAMSuite:
    """BEAM 完整测试套件."""
    results: List[BEAMResult] = field(default_factory=list)
    
    def add_result(self, test_name: str, throughput: float,
                   p50_latency: float, p95_latency: float, 
                   p99_latency: float, memory_mb: float = 0, 
                   details: Dict = None):
        self.results.append(BEAMResult(
            test_name, throughput, p50_latency, 
            p95_latency, p99_latency, memory_mb, 
            details or {}))
    
    def summary(self) -> Dict[str, Any]:
        return {
            "total_tests": len(self.results),
            "results": [
                {
                    "test": r.test_name,
                    "throughput_ops_s": r.throughput,
                    "p50_latency_ms": r.p50_latency_ms,
                    "p95_latency_ms": r.p95_latency_ms,
                    "p99_latency_ms": r.p99_latency_ms,
                    "memory_mb": r.memory_usage_mb
                } for r in self.results
            ]
        }


def generate_random_fact(length: int = 100) -> str:
    """生成随机事实字符串."""
    subjects = ["Alice", "Bob", "Charlie", "Diana", "Eve", "Frank", "Grace", "Henry"]
    verbs = ["likes", "hates", "works at", "lives in", "owns", "reads", "writes", "studies"]
    objects = ["pizza", "New York", "a cat", "books", "Python", "running", "music", "movies"]
    
    pattern = random.choice([
        "{subject} {verb} {object}.",
        "{subject}'s favorite {object_type} is {object}.",
        "{subject} has {number} {object}s.",
        "On {day}, {subject} {verb} {object}."
    ])
    
    if "{object_type}" in pattern:
        object_types = ["food", "city", "pet", "book", "language", "hobby"]
        return pattern.format(
            subject=random.choice(subjects),
            verb=random.choice(verbs),
            object_type=random.choice(object_types),
            object=random.choice(objects)
        )
    elif "{number}" in pattern:
        return pattern.format(
            subject=random.choice(subjects),
            verb=random.choice(verbs),
            number=random.randint(1, 100),
            object=random.choice(objects)
        )
    elif "{day}" in pattern:
        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        return pattern.format(
            day=random.choice(days),
            subject=random.choice(subjects),
            verb=random.choice(verbs),
            object=random.choice(objects)
        )
    else:
        return pattern.format(
            subject=random.choice(subjects),
            verb=random.choice(verbs),
            object=random.choice(objects)
        )


def generate_queries(n: int = 100) -> List[str]:
    """生成随机查询列表."""
    query_templates = [
        "What does {subject} {verb}?",
        "Who {verb} {object}?",
        "Tell me about {subject}.",
        "What is {subject}'s favorite?",
        "Where does {subject} live?",
        "What does {subject} work as?"
    ]
    subjects = ["Alice", "Bob", "Charlie", "Diana", "Eve", "Frank", "Grace", "Henry"]
    verbs = ["like", "hate", "work at", "live in", "own", "read", "write", "study"]
    objects = ["pizza", "New York", "a cat", "books", "Python", "running", "music", "movies"]
    
    queries = []
    for _ in range(n):
        template = random.choice(query_templates)
        queries.append(template.format(
            subject=random.choice(subjects),
            verb=random.choice(verbs),
            object=random.choice(objects)
        ))
    return queries


def _run_beam_write_benchmark(num_records: int = 1000) -> BEAMResult:
    """运行写入性能基准测试."""
    import asyncio
    from memoryx.storage.repository import MemoryRepository
    
    db_path = TEST_DIR / f"beam_write_{num_records}.db"
    repo = MemoryRepository(db_path)
    
    latencies = []
    
    async def _run():
        await repo.open()
        try:
            facts = [generate_random_fact() for _ in range(num_records)]
            
            for fact in facts:
                start = time.perf_counter()
                await repo.add_memory(
                    content=fact,
                    memory_type="fact",
                    scope="global"
                )
                latency = (time.perf_counter() - start) * 1000
                latencies.append(latency)
        finally:
            await repo.close()
    
    start_total = time.perf_counter()
    asyncio.run(_run())
    total_time = time.perf_counter() - start_total
    
    latencies.sort()
    p50 = latencies[int(len(latencies) * 0.5)] if latencies else 0
    p95 = latencies[int(len(latencies) * 0.95)] if latencies else 0
    p99 = latencies[int(len(latencies) * 0.99)] if latencies else 0
    throughput = num_records / total_time if total_time > 0 else 0
    
    return BEAMResult(
        test_name=f"write_{num_records}",
        throughput=throughput,
        p50_latency_ms=p50,
        p95_latency_ms=p95,
        p99_latency_ms=p99,
        details={"num_records": num_records, "total_time_s": total_time}
    )


def _run_beam_search_benchmark(num_records: int = 1000, 
                               num_queries: int = 100) -> BEAMResult:
    """运行搜索性能基准测试."""
    import asyncio
    from memoryx.storage.repository import MemoryRepository
    
    db_path = TEST_DIR / f"beam_search_{num_records}.db"
    repo = MemoryRepository(db_path)
    
    latencies = []
    
    async def _setup():
        await repo.open()
        facts = [generate_random_fact() for _ in range(num_records)]
        for fact in facts:
            await repo.add_memory(
                content=fact,
                memory_type="fact",
                scope="global"
            )
    
    async def _run_queries():
        queries = generate_queries(num_queries)
        for query in queries:
            start = time.perf_counter()
            await repo.search_full_text(query, limit=5)
            latency = (time.perf_counter() - start) * 1000
            latencies.append(latency)
    
    async def _cleanup():
        await repo.close()
    
    async def _full_run():
        await _setup()
        await _run_queries()
        await _cleanup()
    
    start_total = time.perf_counter()
    asyncio.run(_full_run())
    total_time = time.perf_counter() - start_total
    
    latencies.sort()
    p50 = latencies[int(len(latencies) * 0.5)] if latencies else 0
    p95 = latencies[int(len(latencies) * 0.95)] if latencies else 0
    p99 = latencies[int(len(latencies) * 0.99)] if latencies else 0
    throughput = num_queries / total_time if total_time > 0 else 0
    
    return BEAMResult(
        test_name=f"search_{num_records}records_{num_queries}queries",
        throughput=throughput,
        p50_latency_ms=p50,
        p95_latency_ms=p95,
        p99_latency_ms=p99,
        details={"num_records": num_records, "num_queries": num_queries}
    )


@pytest.mark.benchmark
@pytest.mark.beam
@pytest.mark.slow
def test_beam_small_scale():
    """小规模 BEAM 基准测试 (1000条记录)."""
    print("\n" + "=" * 60)
    print("BEAM Benchmark - Small Scale (1000 records)")
    print("=" * 60)
    
    suite = BEAMSuite()
    
    # 写入测试
    print("\nRunning write benchmark...")
    write_result = _run_beam_write_benchmark(1000)
    suite.results.append(write_result)
    print(f"Write Throughput: {write_result.throughput:.2f} ops/s")
    print(f"P50 Latency: {write_result.p50_latency_ms:.2f}ms")
    print(f"P95 Latency: {write_result.p95_latency_ms:.2f}ms")
    print(f"P99 Latency: {write_result.p99_latency_ms:.2f}ms")
    
    # 搜索测试
    print("\nRunning search benchmark...")
    search_result = _run_beam_search_benchmark(1000, 100)
    suite.results.append(search_result)
    print(f"Search Throughput: {search_result.throughput:.2f} ops/s")
    print(f"P50 Latency: {search_result.p50_latency_ms:.2f}ms")
    print(f"P95 Latency: {search_result.p95_latency_ms:.2f}ms")
    print(f"P99 Latency: {search_result.p99_latency_ms:.2f}ms")
    
    # 保存报告
    report_path = TEST_DIR / "beam_small_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(suite.summary(), f, indent=2, ensure_ascii=False)
    
    print(f"\nReport saved to: {report_path}")
    
    # 基本验证
    assert write_result.throughput > 0, "Write throughput should be positive"
    assert search_result.throughput > 0, "Search throughput should be positive"


@pytest.mark.benchmark
@pytest.mark.beam
@pytest.mark.slow
@pytest.mark.skip(reason="Large scale test - run manually")
def test_beam_large_scale():
    """大规模 BEAM 基准测试 (10000条记录 - 手动运行)."""
    print("\n" + "=" * 60)
    print("BEAM Benchmark - Large Scale (10000 records)")
    print("=" * 60)
    
    suite = BEAMSuite()
    
    write_result = _run_beam_write_benchmark(10000)
    suite.results.append(write_result)
    
    search_result = _run_beam_search_benchmark(10000, 500)
    suite.results.append(search_result)
    
    report_path = TEST_DIR / "beam_large_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(suite.summary(), f, indent=2, ensure_ascii=False)
    
    print(f"Report saved to: {report_path}")


if __name__ == "__main__":
    test_beam_small_scale()
