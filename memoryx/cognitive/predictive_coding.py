"""Predictive coding and active inference for memory retrieval.

Based on Friston Free Energy Principle and Predictive Processing:
- Prediction error drives memory updating
- Context expectations bias memory retrieval
- Active inference selects actions minimizing free energy

References:
- Friston, K. (2010). The free-energy principle: a unified brain theory.
- Clark, A. (2013). Whatever next? Predictive brains, situated agents.
- Friston et al. (2017). Active inference: a process theory.
- Barrett & Simmons (2015). Interoceptive predictions in the brain.
"""
from __future__ import annotations
import math
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class PredictionError:
    error: float = 0.0
    surprise: float = 0.0
    precision: float = 1.0
    expected_content: str = ""
    actual_content: str = ""


@dataclass
class ContextExpectation:
    expected_topics: list[str] = field(default_factory=list)
    expected_entities: list[str] = field(default_factory=list)
    confidence: float = 0.5
    context_embedding: list[float] | None = None


class ContextPredictor:
    def __init__(self, decay_rate: float = 0.1):
        self.decay_rate = decay_rate
        self.history: list[dict[str, Any]] = []

    def update(self, query: str, retrieved: list[dict]) -> ContextExpectation:
        self.history.append({"query": query, "retrieved": retrieved, "time": time.time()})
        if len(self.history) > 20:
            self.history = self.history[-20:]
        topics = set()
        for h in self.history[-5:]:
            for r in h.get("retrieved", []):
                content = str(r.get("content", ""))
                topics.update(w.lower().strip(".,!?") for w in content.split() if len(w) > 3)
        common = list(topics)[:10] if topics else query.split()[:5]
        return ContextExpectation(expected_topics=common, confidence=min(1.0, len(self.history) * 0.1))


class PredictiveRetrieval:
    @staticmethod
    def compute_prediction_error(expected: ContextExpectation, memory: dict[str, Any]) -> PredictionError:
        content = str(memory.get("content", "")).lower()
        if not expected.expected_topics:
            return PredictionError(error=0.5, surprise=0.5, precision=0.5)
        topic_hits = sum(1 for t in expected.expected_topics if t.lower() in content)
        hit_ratio = topic_hits / max(len(expected.expected_topics), 1)
        error = 1.0 - hit_ratio
        surprise = -math.log(max(0.01, hit_ratio)) if hit_ratio > 0 else 5.0
        precision = min(1.0, expected.confidence * (1.0 + topic_hits * 0.1))
        return PredictionError(error=error, surprise=min(surprise, 10.0), precision=precision)


class ActiveInferenceGate:
    def __init__(self, free_energy_threshold: float = 0.3):
        self.threshold = free_energy_threshold

    def should_retrieve(self, expected: ContextExpectation) -> bool:
        free_energy = 1.0 - expected.confidence
        return free_energy > self.threshold

    def should_update(self, pe: PredictionError) -> bool:
        free_energy = pe.error * pe.surprise / max(pe.precision, 0.01)
        return free_energy > self.threshold

    def should_ignore(self, pe: PredictionError) -> bool:
        return pe.error < 0.1 and pe.surprise < 1.0

    def free_energy(self, pe: PredictionError) -> float:
        return pe.error * pe.surprise / max(pe.precision, 0.01)
