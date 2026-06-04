from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

@dataclass(frozen=True)
class VectorHit:
    claim_id: str
    score: float

class VectorProvider(Protocol):
    @property
    def available(self) -> bool:
        ...
    def search(self, query: str, limit: int = 20) -> list[VectorHit]:
        ...
    def upsert(self, claim_id: str, content: str) -> None:
        ...
    def delete(self, claim_id: str) -> None:
        ...

class NullVectorProvider:
    @property
    def available(self) -> bool:
        return False
    def search(self, query: str, limit: int = 20) -> list[VectorHit]:
        return []
    def upsert(self, claim_id: str, content: str) -> None:
        return None
    def delete(self, claim_id: str) -> None:
        return None
