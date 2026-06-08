"""Database maintenance stubs for MemoryX e2e testing."""

from __future__ import annotations


class DatabaseMaintenance:
    """Stub for database maintenance operations."""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path

    def run(self) -> None:
        pass

    def stats(self) -> dict[str, int]:
        """Return stub statistics for e2e testing."""
        return {
            "retrieval_events": 0,
            "evidence_events": 0,
            "claims": 0,
            "claim_versions": 0,
        }
