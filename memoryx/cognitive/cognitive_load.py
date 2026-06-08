"""Cognitive load optimization with Miller 7+/-2 chunking.

Optimizes context budget allocation using cognitive load theory.

References:
- Miller (1956). The magical number seven, plus or minus two.
- Sweller (1988). Cognitive load during problem solving.
- Cowan (2001). The magical number 4 in short-term memory.
- Paas et al. (2003). Cognitive load theory and instructional design.
"""
from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import Any

CHUNK_LIMIT = 7


@dataclass
class CognitiveLoadProfile:
    intrinsic_load: float = 0.0
    extraneous_load: float = 0.0
    germane_load: float = 0.0
    total_chunks: int = 0
    recommended_context_budget: int = 4096
    chunk_distribution: list[int] = field(default_factory=lambda: [0]*7)


class CognitiveLoadOptimizer:
    def __init__(self, chunk_limit: int = CHUNK_LIMIT):
        self.chunk_limit = chunk_limit

    def analyze_task(self, task_description: str, chunks: list[dict]) -> CognitiveLoadProfile:
        word_count = len(task_description.split())
        intrinsic = min(1.0, word_count / 100.0)
        extraneous = max(0.0, (len(chunks) - self.chunk_limit) / float(max(self.chunk_limit, 1))) if chunks else 0.0
        n_chunks = min(len(chunks), self.chunk_limit)
        chunk_dist = [0]*self.chunk_limit
        for i in range(min(len(chunks), self.chunk_limit)):
            chunk_dist[i] = 1
        budget = max(1024, min(32768, int(4096 * (1.0 + intrinsic) * (1.0 - extraneous * 0.3))))
        return CognitiveLoadProfile(
            intrinsic_load=intrinsic, extraneous_load=extraneous,
            germane_load=max(0.0, 1.0 - intrinsic - extraneous),
            total_chunks=n_chunks,
            recommended_context_budget=budget,
            chunk_distribution=chunk_dist,
        )

    @staticmethod
    def chunk_items(items: list[str], chunk_size: int = 5) -> list[list[str]]:
        return [items[i:i+chunk_size] for i in range(0, len(items), chunk_size)]

    @staticmethod
    def optimize_budget(current_budget: int, load: CognitiveLoadProfile) -> int:
        if load.total_chunks > CHUNK_LIMIT:
            reduction_factor = CHUNK_LIMIT / max(load.total_chunks, 1)
            return max(1024, int(current_budget * reduction_factor))
        return current_budget

    @staticmethod
    def miller_capacity(chunks: int) -> tuple[int, int]:
        return (max(1, chunks - 2), min(chunks + 2, 9))
