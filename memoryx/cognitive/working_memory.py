"""Baddeley multi-component working memory model.

Implements Baddeley (2000) working memory model:
- Central Executive: attention controller, capacity allocation
- Phonological Loop: verbal/acoustic information (2s loop)
- Visuospatial Sketchpad: visual/spatial information
- Episodic Buffer: multi-dimensional episodic integration

Capacity limits follow Miller (1956) 7+/-2 chunking.
Time limits follow Baddeley (1992) 2-second phonological loop.

References:
- Baddeley, A. D. (2000). The episodic buffer: a new component of working memory?
- Baddeley, A. D. (1992). Working memory. Science, 255(5044), 556-559.
- Miller, G. A. (1956). The magical number seven, plus or minus two.
- Cowan, N. (2001). The magical number 4 in short-term memory.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class WorkingMemoryComponent(Enum):
    CENTRAL_EXECUTIVE = "central_executive"
    PHONOLOGICAL_LOOP = "phonological_loop"
    VISUOSPATIAL_SKETCHPAD = "visuospatial_sketchpad"
    EPISODIC_BUFFER = "episodic_buffer"


class ModalityType(Enum):
    VERBAL = "verbal"
    VISUAL = "visual"
    SPATIAL = "spatial"
    EPISODIC = "episodic"
    ABSTRACT = "abstract"


@dataclass
class WorkingMemoryChunk:
    chunk_id: str = ""
    content: str = ""
    modality: ModalityType = ModalityType.ABSTRACT
    chunk_size: int = 1
    importance: float = 0.5
    created_at: float = 0.0
    expires_at: float = 0.0
    source: str = ""


@dataclass
class WorkingMemoryState:
    phonological_loop: list[WorkingMemoryChunk] = field(default_factory=list)
    visuospatial_sketchpad: list[WorkingMemoryChunk] = field(default_factory=list)
    episodic_buffer: list[WorkingMemoryChunk] = field(default_factory=list)
    central_executive_load: float = 0.0
    total_capacity: int = 7
    max_chunks: int = 4

    def total_load(self) -> int:
        return len(self.phonological_loop) + len(self.visuospatial_sketchpad) + len(self.episodic_buffer)

    def is_available(self) -> bool:
        return self.total_load() < self.total_capacity


class PhonologicalLoop:
    LOOP_DURATION = 2.0

    @staticmethod
    def can_hold(content: str, loop_duration: float = LOOP_DURATION) -> bool:
        words = len(content.split())
        articulation_rate = 3.0
        estimated_time = words / articulation_rate
        return estimated_time <= loop_duration

    @staticmethod
    def encode(content: str, chunk_size: int = 1) -> list[WorkingMemoryChunk]:
        chunks = []
        words = content.split()
        for i in range(0, len(words), chunk_size):
            segment = " ".join(words[i:i+chunk_size])
            chunks.append(WorkingMemoryChunk(
                chunk_id=f"phon_{i//chunk_size}",
                content=segment,
                modality=ModalityType.VERBAL,
                chunk_size=chunk_size,
            ))
        return chunks


class VisuospatialSketchpad:
    CAPACITY = 4

    @staticmethod
    def encode(content: str) -> list[WorkingMemoryChunk]:
        return [WorkingMemoryChunk(
            chunk_id="vis_0",
            content=content,
            modality=ModalityType.VISUAL,
            chunk_size=min(len(content.split()), 4),
        )]


class EpisodicBuffer:
    CAPACITY = 4

    @staticmethod
    def bind(phonological: list, visuospatial: list) -> list[WorkingMemoryChunk]:
        episodes = []
        for i, (p, v) in enumerate(zip(phonological[:EpisodicBuffer.CAPACITY], visuospatial[:EpisodicBuffer.CAPACITY])):
            episodes.append(WorkingMemoryChunk(
                chunk_id=f"epi_{i}",
                content=f"{p.content} | {v.content}",
                modality=ModalityType.EPISODIC,
                chunk_size=p.chunk_size + v.chunk_size,
                importance=max(p.importance, v.importance),
            ))
        return episodes


class CentralExecutive:
    def __init__(self, capacity: int = 7, max_chunks: int = 4):
        self.capacity = capacity
        self.max_chunks = max_chunks

    def allocate(self, state: WorkingMemoryState, chunks: list[WorkingMemoryChunk]) -> WorkingMemoryState:
        available = self.capacity - state.total_load()
        for chunk in chunks:
            if available <= 0:
                break
            if chunk.modality == ModalityType.VERBAL:
                state.phonological_loop.append(chunk)
            elif chunk.modality in (ModalityType.VISUAL, ModalityType.SPATIAL):
                state.visuospatial_sketchpad.append(chunk)
            elif chunk.modality == ModalityType.EPISODIC:
                state.episodic_buffer.append(chunk)
            available -= chunk.chunk_size
        state.central_executive_load = state.total_load() / self.capacity
        return state

    def prune_expired(self, state: WorkingMemoryState, now: float | None = None) -> WorkingMemoryState:
        if now is None:
            now = time.time()
        state.phonological_loop = [c for c in state.phonological_loop if c.expires_at <= 0 or c.expires_at > now]
        state.visuospatial_sketchpad = [c for c in state.visuospatial_sketchpad if c.expires_at <= 0 or c.expires_at > now]
        state.episodic_buffer = [c for c in state.episodic_buffer if c.expires_at <= 0 or c.expires_at > now]
        state.central_executive_load = state.total_load() / self.capacity if self.capacity > 0 else 0.0
        return state

    def capacity_remaining(self, state: WorkingMemoryState) -> int:
        return max(0, self.capacity - state.total_load())


class BaddeleyWorkingMemory:
    def __init__(self, capacity: int = 7, max_chunks: int = 4):
        self.phonological_loop = PhonologicalLoop()
        self.visuospatial_sketchpad = VisuospatialSketchpad()
        self.episodic_buffer = EpisodicBuffer()
        self.central_executive = CentralExecutive(capacity, max_chunks)
        self.state = WorkingMemoryState(total_capacity=capacity, max_chunks=max_chunks)

    def process(self, content: str, modality: ModalityType = ModalityType.VERBAL) -> WorkingMemoryState:
        if modality == ModalityType.VERBAL:
            chunks = self.phonological_loop.encode(content)
        elif modality in (ModalityType.VISUAL, ModalityType.SPATIAL):
            chunks = self.visuospatial_sketchpad.encode(content)
        else:
            chunks = [WorkingMemoryChunk(content=content, modality=modality)]
        self.state = self.central_executive.allocate(self.state, chunks)
        return self.state

    def bind_episodes(self) -> list[WorkingMemoryChunk]:
        episodes = self.episodic_buffer.bind(self.state.phonological_loop, self.state.visuospatial_sketchpad)
        self.state = self.central_executive.allocate(self.state, episodes)
        return episodes

    def prune(self) -> WorkingMemoryState:
        self.state = self.central_executive.prune_expired(self.state)
        return self.state

    def clear(self) -> None:
        self.state = WorkingMemoryState(total_capacity=self.state.total_capacity)

    def remaining_capacity(self) -> int:
        return self.central_executive.capacity_remaining(self.state)

    def is_overloaded(self) -> bool:
        return self.state.central_executive_load > 0.85

    def to_dict(self) -> dict[str, Any]:
        return {
            "phonological_loop": len(self.state.phonological_loop),
            "visuospatial_sketchpad": len(self.state.visuospatial_sketchpad),
            "episodic_buffer": len(self.state.episodic_buffer),
            "central_executive_load": self.state.central_executive_load,
            "remaining_capacity": self.remaining_capacity(),
            "is_overloaded": self.is_overloaded(),
        }
