"""Tests for predictive coding and active inference."""
from __future__ import annotations
import pytest
from memoryx.cognitive.predictive_coding import (
    ActiveInferenceGate, ContextExpectation, ContextPredictor,
    PredictionError, PredictiveRetrieval,
)


class TestContextPredictor:
    def test_update_creates_expectation(self):
        cp = ContextPredictor()
        exp = cp.update("hello world", [{"content": "hello world test"}])
        assert len(exp.expected_topics) > 0
        assert exp.confidence > 0

    def test_empty_history_low_confidence(self):
        cp = ContextPredictor()
        assert cp.history == []


class TestPredictiveRetrieval:
    def test_compute_prediction_error_no_topics(self):
        exp = ContextExpectation(expected_topics=[])
        pe = PredictiveRetrieval.compute_prediction_error(exp, {"content": "test"})
        assert pe.error == 0.5

    def test_compute_prediction_error_match(self):
        exp = ContextExpectation(expected_topics=["hello", "world"])
        pe = PredictiveRetrieval.compute_prediction_error(exp, {"content": "hello world"})
        assert pe.error < 0.5

    def test_compute_prediction_error_no_match(self):
        exp = ContextExpectation(expected_topics=["hello"])
        pe = PredictiveRetrieval.compute_prediction_error(exp, {"content": "other thing"})
        assert pe.error == 1.0


class TestActiveInferenceGate:
    def test_should_retrieve_low_confidence(self):
        gate = ActiveInferenceGate(0.3)
        exp = ContextExpectation(confidence=0.1)
        assert gate.should_retrieve(exp) == True

    def test_should_retrieve_high_confidence(self):
        gate = ActiveInferenceGate(0.3)
        exp = ContextExpectation(confidence=0.9)
        assert gate.should_retrieve(exp) == False

    def test_should_update_high_error(self):
        gate = ActiveInferenceGate(0.3)
        pe = PredictionError(error=0.8, surprise=3.0, precision=0.5)
        assert gate.should_update(pe) == True

    def test_should_ignore_low_error(self):
        gate = ActiveInferenceGate()
        pe = PredictionError(error=0.05, surprise=0.5, precision=1.0)
        assert gate.should_ignore(pe) == True

    def test_free_energy_calculation(self):
        gate = ActiveInferenceGate()
        pe = PredictionError(error=0.5, surprise=2.0, precision=1.0)
        fe = gate.free_energy(pe)
        assert fe == 1.0
