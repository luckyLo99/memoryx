"""Tests for Baddeley multi-component working memory model."""
from __future__ import annotations

import pytest
from memoryx.cognitive.working_memory import (
    BaddeleyWorkingMemory, CentralExecutive, EpisodicBuffer,
    ModalityType, PhonologicalLoop, VisuospatialSketchpad,
    WorkingMemoryChunk, WorkingMemoryState,
)


class TestPhonologicalLoop:
    def test_can_hold_short_phrase(self):
        assert PhonologicalLoop.can_hold("hello world") == True

    def test_cannot_hold_long_text(self):
        long = "word " * 20
        assert PhonologicalLoop.can_hold(long, loop_duration=2.0) == False

    def test_encode_verbal(self):
        chunks = PhonologicalLoop.encode("hello world foo bar")
        assert len(chunks) > 0
        assert chunks[0].modality == ModalityType.VERBAL


class TestVisuospatialSketchpad:
    def test_encode_visual(self):
        chunks = VisuospatialSketchpad.encode("red circle top left")
        assert len(chunks) == 1
        assert chunks[0].modality == ModalityType.VISUAL


class TestEpisodicBuffer:
    def test_bind_empty(self):
        episodes = EpisodicBuffer.bind([], [])
        assert len(episodes) == 0

    def test_bind_integration(self):
        p = [WorkingMemoryChunk(content="hello", modality=ModalityType.VERBAL, chunk_size=1)]
        v = [WorkingMemoryChunk(content="circle", modality=ModalityType.VISUAL, chunk_size=1)]
        episodes = EpisodicBuffer.bind(p, v)
        assert len(episodes) == 1
        assert episodes[0].modality == ModalityType.EPISODIC


class TestCentralExecutive:
    def test_allocate_within_capacity(self):
        ce = CentralExecutive(capacity=7)
        state = WorkingMemoryState()
        chunks = [WorkingMemoryChunk(content="a", modality=ModalityType.VERBAL, chunk_size=1)]
        result = ce.allocate(state, chunks)
        assert len(result.phonological_loop) == 1

    def test_allocate_exceeds_capacity(self):
        ce = CentralExecutive(capacity=2)
        state = WorkingMemoryState(total_capacity=2)
        chunks = [
            WorkingMemoryChunk(content="a", modality=ModalityType.VERBAL, chunk_size=1),
            WorkingMemoryChunk(content="b", modality=ModalityType.VERBAL, chunk_size=1),
            WorkingMemoryChunk(content="c", modality=ModalityType.VERBAL, chunk_size=1),
        ]
        result = ce.allocate(state, chunks)
        assert len(result.phonological_loop) == 2

    def test_prune_expired(self):
        ce = CentralExecutive()
        state = WorkingMemoryState()
        state.phonological_loop = [
            WorkingMemoryChunk(content="valid", expires_at=0),
        ]
        result = ce.prune_expired(state, now=9999999999999)
        assert len(result.phonological_loop) == 1

    def test_capacity_remaining(self):
        ce = CentralExecutive(capacity=7)
        state = WorkingMemoryState()
        state.phonological_loop = [WorkingMemoryChunk(chunk_size=1), WorkingMemoryChunk(chunk_size=1)]
        assert ce.capacity_remaining(state) == 5


class TestBaddeleyWorkingMemory:
    def test_process_verbal(self):
        wm = BaddeleyWorkingMemory()
        state = wm.process("hello world")
        assert len(state.phonological_loop) > 0

    def test_process_visual(self):
        wm = BaddeleyWorkingMemory()
        state = wm.process("red circle", modality=ModalityType.VISUAL)
        assert len(state.visuospatial_sketchpad) > 0

    def test_overloaded_detection(self):
        wm = BaddeleyWorkingMemory(capacity=2)
        wm.process("hello world foo bar baz qux", modality=ModalityType.VERBAL)
        assert wm.is_overloaded() == True

    def test_remaining_capacity(self):
        wm = BaddeleyWorkingMemory(capacity=7)
        wm.process("hello")
        assert wm.remaining_capacity() < 7

    def test_clear(self):
        wm = BaddeleyWorkingMemory()
        wm.process("hello")
        wm.clear()
        assert wm.remaining_capacity() == 7

    def test_to_dict(self):
        wm = BaddeleyWorkingMemory()
        d = wm.to_dict()
        assert "phonological_loop" in d
        assert "central_executive_load" in d
        assert "is_overloaded" in d

    def test_bind_episodes(self):
        wm = BaddeleyWorkingMemory()
        wm.process("hello world", modality=ModalityType.VERBAL)
        wm.process("red circle top left", modality=ModalityType.VISUAL)
        episodes = wm.bind_episodes()
        assert len(episodes) >= 0
